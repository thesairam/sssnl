import 'dart:async';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:video_player/video_player.dart';

void main() {
  runApp(const SssnlApp());
}

/// Backend base URL: dynamically use current origin for Flutter Web.
const String _kBackendBaseUrlEnv = String.fromEnvironment('BACKEND_BASE_URL', defaultValue: '');
final String kBackendBaseUrl = _kBackendBaseUrlEnv.isNotEmpty ? _kBackendBaseUrlEnv : Uri.base.origin;
final String? kDeviceMacParam = Uri.base.queryParameters['device_mac'];

class SssnlApp extends StatelessWidget {
  const SssnlApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'SSSNL Dashboard',
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: const Color(0xFF020617),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFFF97316),
          secondary: Color(0xFF22C55E),
        ),
      ),
      // Show dashboard directly; no login required here.
      home: const DashboardScreen(),
    );
  }
}

class _DashboardAuthGate extends StatefulWidget {
  const _DashboardAuthGate();

  @override
  State<_DashboardAuthGate> createState() => _DashboardAuthGateState();
}

class _DashboardAuthGateState extends State<_DashboardAuthGate> {
  bool _authed = false;
  bool _loading = true;
  String? _error;
  final _userCtrl = TextEditingController(text: 'dev');
  final _passCtrl = TextEditingController(text: 'dev123');

  @override
  void initState() {
    super.initState();
    _checkAuth();
  }

  Future<void> _checkAuth() async {
    setState(() { _loading = true; _error = null; });
    try {
      final resp = await http.get(Uri.parse('$kBackendBaseUrl/api/auth/me')).timeout(const Duration(seconds: 8));
      setState(() { _authed = resp.statusCode == 200; });
    } catch (_) {
      setState(() { _authed = false; });
    } finally {
      setState(() { _loading = false; });
    }
  }

  Future<void> _login() async {
    setState(() { _loading = true; _error = null; });
    try {
      final resp = await http.post(
        Uri.parse('$kBackendBaseUrl/api/auth/login'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'username': _userCtrl.text.trim(), 'password': _passCtrl.text}),
      ).timeout(const Duration(seconds: 8));
      if (resp.statusCode == 200) {
        setState(() { _authed = true; });
      } else {
        setState(() { _error = 'Login failed (${resp.statusCode})'; });
      }
    } catch (e) {
      setState(() { _error = 'Login error: $e'; });
    } finally {
      setState(() { _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_authed) return const DashboardScreen();
    return Scaffold(
      appBar: AppBar(title: const Text('Dashboard Login')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 360),
          child: Card(
            color: const Color(0xFF020617),
            elevation: 8,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text('Sign In', textAlign: TextAlign.center, style: TextStyle(fontSize: 20, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 12),
                  TextField(controller: _userCtrl, decoration: const InputDecoration(labelText: 'Username')),
                  const SizedBox(height: 8),
                  TextField(controller: _passCtrl, decoration: const InputDecoration(labelText: 'Password'), obscureText: true),
                  const SizedBox(height: 12),
                  ElevatedButton(onPressed: _loading ? null : _login, child: const Text('Enter')),
                  if (_loading) ...[
                    const SizedBox(height: 12),
                    const Center(child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))),
                  ],
                  if (_error != null) ...[
                    const SizedBox(height: 8),
                    Text(_error!, style: const TextStyle(color: Colors.redAccent, fontSize: 12)),
                  ]
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class PlaylistItem {
  final String type; // 'video' or 'image'
  final String src; // relative URL from backend
  final int? durationMs; // for images

  const PlaylistItem({
    required this.type,
    required this.src,
    this.durationMs,
  });

  String get fullUrl => '$kBackendBaseUrl$src';

  static PlaylistItem fromJson(Map<String, dynamic> json) {
    return PlaylistItem(
      type: json['type'] as String? ?? 'image',
      src: json['src'] as String? ?? '',
      durationMs: (json['duration_ms'] as num?)?.toInt(),
    );
  }
}

class StatusData {
  final String temp;
  final String hum;
  final String motionStatus;
  final bool motionActive;

  const StatusData({
    required this.temp,
    required this.hum,
    required this.motionStatus,
    required this.motionActive,
  });

  factory StatusData.fromJson(Map<String, dynamic> json) {
    return StatusData(
      temp: json['temp'] as String? ?? '--',
      hum: json['hum'] as String? ?? '--',
      motionStatus: json['motion_status'] as String? ?? 'No motion',
      motionActive: json['motion_active'] as bool? ?? false,
    );
  }
}

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  StatusData _status = const StatusData(
    temp: '--',
    hum: '--',
    motionStatus: 'No motion',
    motionActive: false,
  );

  Timer? _statusTimer;
  bool _playing = false;
  bool _motionTriggered = false;
  VideoPlayerController? _videoController;
  PlaylistItem? _currentItem;

  @override
  void initState() {
    super.initState();
    _startStatusPolling();
  }

  @override
  void dispose() {
    _statusTimer?.cancel();
    _videoController?.dispose();
    super.dispose();
  }

  void _startStatusPolling() {
    // Initial fetch
    _fetchStatus();
    _statusTimer?.cancel();
    _statusTimer = Timer.periodic(const Duration(milliseconds: 1500), (_) {
      _fetchStatus();
    });
  }

  Future<void> _fetchStatus() async {
    try {
      final resp = await http.get(Uri.parse('$kBackendBaseUrl/status'));
      if (resp.statusCode != 200) return;
      final data = json.decode(resp.body) as Map<String, dynamic>;
      final newStatus = StatusData.fromJson(data);

      final bool oldMotion = _status.motionActive;
      setState(() {
        _status = newStatus;
      });

      // Rising edge: start playlist once if not currently playing.
      if (newStatus.motionActive && !oldMotion && !_playing && !_motionTriggered) {
        _playPlaylistOnce();
      }
    } catch (_) {
      // ignore errors; keep last known status
    }
  }

  Future<List<PlaylistItem>> _fetchPlaylist() async {
    try {
      final bool hasMac = kDeviceMacParam != null && kDeviceMacParam!.isNotEmpty;
      final Uri uri = hasMac
          ? Uri.parse('$kBackendBaseUrl/api/public/playlist_by_mac').replace(queryParameters: {'mac': kDeviceMacParam!})
          : Uri.parse('$kBackendBaseUrl/playlist');
      final resp = await http.get(uri).timeout(const Duration(seconds: 12));
      if (resp.statusCode != 200) return const [];
      final data = json.decode(resp.body) as Map<String, dynamic>;
      final list = data['playlist'] as List<dynamic>? ?? const [];
      return list
          .whereType<Map<String, dynamic>>()
          .map(PlaylistItem.fromJson)
          .toList(growable: false);
    } catch (_) {
      return const [];
    }
  }

  Future<void> _playPlaylistOnce() async {
    if (_playing) return;
    setState(() {
      _playing = true;
      _motionTriggered = true;
    });

    final playlist = await _fetchPlaylist();
    for (final item in playlist) {
      if (!mounted) break;
      if (item.type == 'video') {
        await _playVideoItem(item);
      } else {
        await _showImageItem(item);
      }
    }

    if (!mounted) return;
    setState(() {
      _playing = false;
      _motionTriggered = false;
      _currentItem = null;
    });
  }

  Future<void> _playVideoItem(PlaylistItem item) async {
    _videoController?.dispose();
    _videoController = VideoPlayerController.networkUrl(Uri.parse(item.fullUrl));
    setState(() {
      _currentItem = item;
    });

    try {
      await _videoController!.initialize();
      await _videoController!.play();

      // Wait until the video ends or a max timeout.
      final duration = _videoController!.value.duration;
      final maxWait = duration == Duration.zero
          ? const Duration(seconds: 45)
          : duration + const Duration(seconds: 3);

      final completer = Completer<void>();
      void listener() {
        if (_videoController == null) return;
        if (_videoController!.value.position >=
            _videoController!.value.duration) {
          if (!completer.isCompleted) {
            completer.complete();
          }
        }
      }

      _videoController!.addListener(listener);

      await Future.any([
        completer.future,
        Future.delayed(maxWait),
      ]);

      _videoController!.removeListener(listener);
      await _videoController!.pause();
    } catch (_) {
      // ignore, move to next item
    }
  }

  Future<void> _showImageItem(PlaylistItem item) async {
    setState(() {
      _videoController?.dispose();
      _videoController = null;
      _currentItem = item;
    });
    final ms = item.durationMs ?? 6000;
    await Future.delayed(Duration(milliseconds: ms));
  }

  @override
  Widget build(BuildContext context) {
    final isVideo = _currentItem?.type == 'video' && _videoController != null;

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            _StatusBar(status: _status),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
              color: const Color(0xFF0F172A),
              child: const Text(
                "🌼 Don't forget to turn off Diyas & close doors 🌼",
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
              ),
            ),
            Expanded(
              child: Container(
                color: const Color(0xFF020617),
                alignment: Alignment.center,
                child: _playing && _currentItem != null
                    ? AspectRatio(
                        aspectRatio: isVideo
                            ? (_videoController!.value.isInitialized
                                ? _videoController!.value.aspectRatio
                                : 16 / 9)
                            : 16 / 9,
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(12),
                          child: DecoratedBox(
                            decoration: const BoxDecoration(
                              color: Colors.black,
                            ),
                            child: isVideo
                                ? VideoPlayer(_videoController!)
                                : FittedBox(
                                    fit: BoxFit.contain,
                                    child: Image.network(
                                      _currentItem!.fullUrl,
                                      fit: BoxFit.contain,
                                      errorBuilder: (_, __, ___) => const Center(
                                        child: Icon(
                                          Icons.broken_image,
                                          color: Colors.white54,
                                          size: 64,
                                        ),
                                      ),
                                    ),
                                  ),
                          ),
                        ),
                      )
                    : const _IdleMessage(),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StatusBar extends StatelessWidget {
  final StatusData status;

  const _StatusBar({required this.status});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      color: const Color(0xFF0B1120),
      child: DefaultTextStyle(
        style: const TextStyle(fontSize: 16, color: Colors.white),
        child: Wrap(
          alignment: WrapAlignment.center,
          spacing: 16,
          runSpacing: 8,
          children: [
            Text('Temp: ${status.temp}'),
            Text('Humidity: ${status.hum}'),
            Text('Motion: ${status.motionStatus}'),
          ],
        ),
      ),
    );
  }
}

class _IdleMessage extends StatelessWidget {
  const _IdleMessage();

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: const [
        Icon(Icons.nightlight_round,
            size: 64, color: Color(0xFF64748B)),
        SizedBox(height: 16),
        Text(
          'Awaiting motion…',
          style: TextStyle(
            fontSize: 22,
            fontWeight: FontWeight.w600,
            color: Color(0xFFCBD5F5),
          ),
        ),
      ],
    );
  }
}
