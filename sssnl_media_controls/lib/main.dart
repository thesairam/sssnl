import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'settings.dart';

void main() {
  runApp(const MediaControlsApp());
}

/// Backend base URL:
/// - On Web: uses current origin (same-host Flask)
/// - On Mobile/Desktop: prefer BACKEND_BASE_URL from --dart-define
const String _kBackendBaseUrlEnv = String.fromEnvironment('BACKEND_BASE_URL', defaultValue: '');
final String kBackendBaseUrl = _kBackendBaseUrlEnv.isNotEmpty ? _kBackendBaseUrlEnv : Uri.base.origin;

// Dummy dev credentials (front-end only, not secure).
const String kDevUsername = 'dev';
const String kDevPassword = 'dev123';

class MediaControlsApp extends StatelessWidget {
  const MediaControlsApp({super.key});

  @override
  Widget build(BuildContext context) {
    final path = Uri.base.path.toLowerCase();
    final isDev = path.contains('/dev');
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: isDev ? 'SSSNL Dev Controls' : 'SSSNL Media Manager',
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: const Color(0xFF020617),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF3B82F6),
          secondary: Color(0xFFF97316),
        ),
      ),
      // Main app: auth gate leads to home menu; dev route keeps existing login
      home: isDev ? const _LoginScreen() : const _AuthGate(),
    );
  }
}

/// Simple cookie store and client to persist Flask session across requests.
class _CookieStore {
  static const _cookieKey = 'session_cookie';
  static String? _cookie; // in-memory cache: 'session=...'

  static Future<String?> get() async {
    if (_cookie != null) return _cookie;
    final prefs = await SharedPreferences.getInstance();
    _cookie = prefs.getString(_cookieKey);
    return _cookie;
  }

  static Future<void> set(String? cookie) async {
    _cookie = cookie;
    final prefs = await SharedPreferences.getInstance();
    if (cookie == null || cookie.isEmpty) {
      await prefs.remove(_cookieKey);
    } else {
      await prefs.setString(_cookieKey, cookie);
    }
  }

  static Map<String, String>? peekHeader() {
    if (_cookie == null || _cookie!.isEmpty) return null;
    return {'Cookie': _cookie!};
  }
}

class _CookieClient extends http.BaseClient {
  final http.Client _inner = http.Client();

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    // Attach cookie if present
    final cookie = await _CookieStore.get();
    if (cookie != null && cookie.isNotEmpty) {
      request.headers.putIfAbsent('Cookie', () => cookie);
    }

    final resp = await _inner.send(request);

    // Capture Set-Cookie (Flask session). Some stacks send multiple cookies
    // in a single header; search for 'session=' anywhere.
    try {
      final setCookie = resp.headers['set-cookie'];
      if (setCookie != null && setCookie.isNotEmpty) {
        final match = RegExp(r'session=([^;]+)', caseSensitive: false)
            .firstMatch(setCookie);
        final value = match?.group(1);
        if (value != null && value.isNotEmpty) {
          await _CookieStore.set('session=$value');
        }
      }
    } catch (_) {
      // ignore parsing errors
    }

    return resp;
  }
}

final http.Client _api = _CookieClient();

class _AuthGate extends StatefulWidget {
  const _AuthGate();

  @override
  State<_AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<_AuthGate> {
  bool _authed = false;
  bool _loading = true;
  String? _error;
  final _userCtrl = TextEditingController();
  final _passCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _checkAuth();
  }

  Future<void> _checkAuth() async {
    setState(() { _loading = true; _error = null; });
    try {
      final resp = await _api.get(Uri.parse('$kBackendBaseUrl/api/auth/me')).timeout(const Duration(seconds: 8));
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
      final resp = await _api.post(
        Uri.parse('$kBackendBaseUrl/api/auth/login'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'username': _userCtrl.text.trim(), 'password': _passCtrl.text}),
      ).timeout(const Duration(seconds: 8));
      if (resp.statusCode == 200) {
        if (!mounted) return;
        Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => const _HomeMenuPage()));
      } else {
        setState(() { _error = 'Login failed (${resp.statusCode})'; });
      }
    } catch (e) {
      setState(() { _error = 'Login error: $e'; });
    } finally {
      setState(() { _loading = false; });
    }
  }

  Future<void> _signup() async {
    setState(() { _loading = true; _error = null; });
    try {
      final resp = await _api.post(
        Uri.parse('$kBackendBaseUrl/api/auth/signup'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'username': _userCtrl.text.trim(), 'password': _passCtrl.text}),
      ).timeout(const Duration(seconds: 8));
      if (resp.statusCode == 200) {
        if (!mounted) return;
        Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => const _HomeMenuPage()));
      } else {
        setState(() { _error = 'Signup failed (${resp.statusCode})'; });
      }
    } catch (e) {
      setState(() { _error = 'Signup error: $e'; });
    } finally {
      setState(() { _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_authed) return const _HomeMenuPage();
    return Scaffold(
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
                  const Text('Sign In / Sign Up', textAlign: TextAlign.center, style: TextStyle(fontSize: 20, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 12),
                  TextField(controller: _userCtrl, decoration: const InputDecoration(labelText: 'Username')),
                  const SizedBox(height: 8),
                  TextField(controller: _passCtrl, decoration: const InputDecoration(labelText: 'Password'), obscureText: true),
                  const SizedBox(height: 12),
                  Row(children: [
                    ElevatedButton(onPressed: _loading ? null : _login, child: const Text('Sign In')),
                    const SizedBox(width: 8),
                    OutlinedButton(onPressed: _loading ? null : _signup, child: const Text('Sign Up')),
                    if (_loading) ...[
                      const SizedBox(width: 12),
                      const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
                    ],
                  ]),
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

class _HomeMenuPage extends StatelessWidget {
  const _HomeMenuPage();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('SSSNL')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('Choose an action', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
            const SizedBox(height: 12),
            ElevatedButton.icon(
              onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const _DeviceListPage())),
              icon: const Icon(Icons.devices),
              label: const Text('Choose Device'),
            ),
            const SizedBox(height: 8),
            ElevatedButton.icon(
              onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const DevicePairingPage())),
              icon: const Icon(Icons.bluetooth),
              label: const Text('Add Device (Setup)'),
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const _MediaManagerPage())),
              icon: const Icon(Icons.perm_media),
              label: const Text('Open Media Controls'),
            ),
          ],
        ),
      ),
    );
  }
}

class _DeviceListPage extends StatefulWidget {
  const _DeviceListPage();

  @override
  State<_DeviceListPage> createState() => _DeviceListPageState();
}

class _DeviceListPageState extends State<_DeviceListPage> {
  List<Map<String, dynamic>> _devices = const [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final resp = await _api.get(Uri.parse('$kBackendBaseUrl/api/devices')).timeout(const Duration(seconds: 10));
      if (resp.statusCode == 200) {
        final data = json.decode(resp.body) as Map<String, dynamic>;
        setState(() { _devices = (data['devices'] as List).cast<Map<String, dynamic>>(); });
      } else {
        setState(() { _error = 'List failed (${resp.statusCode})'; });
      }
    } catch (e) {
      setState(() { _error = 'Load error: $e'; });
    } finally {
      setState(() { _loading = false; });
    }
  }

  Future<void> _select(Map<String, dynamic> d) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('device_mac', (d['mac'] as String?) ?? '');
    await prefs.setString('device_id', (d['device_id'] as String?) ?? '');
    if (!mounted) return;
    Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => const _MediaManagerPage()));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Choose Device')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _devices.isEmpty
              ? Center(child: Text(_error ?? 'No devices found'))
              : ListView.builder(
                  itemCount: _devices.length,
                  itemBuilder: (ctx, i) {
                    final d = _devices[i];
                    return ListTile(
                      leading: const Icon(Icons.device_hub),
                      title: Text(d['name'] as String? ?? d['mac'] as String? ?? ''),
                      subtitle: Text('MAC: ${d['mac'] ?? ''}  •  status: ${d['status'] ?? 'unknown'}'),
                      trailing: ElevatedButton(onPressed: () => _select(d), child: const Text('Select')),
                    );
                  },
                ),
    );
  }
}

class _LoginScreen extends StatefulWidget {
  const _LoginScreen();

  @override
  State<_LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<_LoginScreen> {
  final _userCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  String? _error;
  bool _loading = false;

  void _submit() {
    setState(() { _error = null; _loading = true; });
    _api
        .post(
          Uri.parse('$kBackendBaseUrl/api/auth/login'),
          headers: {'Content-Type': 'application/json'},
          body: json.encode({'username': _userCtrl.text.trim(), 'password': _passCtrl.text}),
        )
        .timeout(const Duration(seconds: 10))
        .then((resp) {
      if (resp.statusCode == 200) {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => const _DevControlsPage()),
        );
      } else {
        setState(() { _error = 'Sign in failed (${resp.statusCode})'; });
      }
    }).catchError((e) {
      setState(() { _error = 'Sign in error: $e'; });
    }).whenComplete(() {
      setState(() { _loading = false; });
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 360),
          child: Card(
            color: const Color(0xFF020617),
            elevation: 8,
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text(
                    'Developer Login',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: _userCtrl,
                    decoration: const InputDecoration(labelText: 'Username'),
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: _passCtrl,
                    decoration: const InputDecoration(labelText: 'Password'),
                    obscureText: true,
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 8),
                    Text(
                      _error!,
                      style:
                          const TextStyle(color: Colors.redAccent, fontSize: 13),
                    ),
                  ],
                  const SizedBox(height: 16),
                  ElevatedButton(
                    onPressed: _submit,
                    child: const Text('Enter'),
                  ),
                  if (_loading) ...[
                    const SizedBox(height: 12),
                    const Center(child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// Removed combined shell to avoid duplication; routing now selects a single page.

class _MediaFile {
  final String name;
  final String url;
  final String type; // image or video

  _MediaFile({required this.name, required this.url, required this.type});

  factory _MediaFile.fromJson(Map<String, dynamic> json) => _MediaFile(
        name: json['name'] as String? ?? '',
        url: json['url'] as String? ?? '',
        type: json['type'] as String? ?? 'image',
      );
}

class _MediaManagerPage extends StatefulWidget {
  const _MediaManagerPage();

  @override
  State<_MediaManagerPage> createState() => _MediaManagerPageState();
}

class _MediaManagerPageState extends State<_MediaManagerPage> {
  List<_MediaFile> _files = const [];
  bool _loading = false;
  bool _authed = false;
  bool _authLoading = false;
  String? _authError;
  final _userCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  String? _deviceMac;

  @override
  void initState() {
    super.initState();
    _checkAuth().then((_) { if (_authed) _refresh(); });
  }

  Future<void> _checkAuth() async {
    setState(() { _authLoading = true; _authError = null; });
    try {
      final resp = await _api.get(Uri.parse('$kBackendBaseUrl/api/auth/me')).timeout(const Duration(seconds: 10));
      setState(() { _authed = resp.statusCode == 200; });
    } catch (_) {
      setState(() { _authed = false; });
    } finally {
      setState(() { _authLoading = false; });
    }
  }

  Future<void> _login() async {
    setState(() { _authLoading = true; _authError = null; });
    try {
      final resp = await _api.post(
        Uri.parse('$kBackendBaseUrl/api/auth/login'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'username': _userCtrl.text.trim(), 'password': _passCtrl.text}),
      ).timeout(const Duration(seconds: 10));
      if (resp.statusCode == 200) {
        setState(() { _authed = true; });
        await _refresh();
      } else {
        setState(() { _authError = 'Login failed (${resp.statusCode})'; });
      }
    } catch (e) {
      setState(() { _authError = 'Login error: $e'; });
    } finally {
      setState(() { _authLoading = false; });
    }
  }

  Future<void> _signup() async {
    setState(() { _authLoading = true; _authError = null; });
    try {
      final resp = await _api.post(
        Uri.parse('$kBackendBaseUrl/api/auth/signup'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'username': _userCtrl.text.trim(), 'password': _passCtrl.text}),
      ).timeout(const Duration(seconds: 10));
      if (resp.statusCode == 200) {
        setState(() { _authed = true; });
        await _refresh();
      } else {
        setState(() { _authError = 'Signup failed (${resp.statusCode})'; });
      }
    } catch (e) {
      setState(() { _authError = 'Signup error: $e'; });
    } finally {
      setState(() { _authLoading = false; });
    }
  }

  Future<void> _refresh() async {
    setState(() => _loading = true);
    try {
        final prefs = await SharedPreferences.getInstance();
        _deviceMac = prefs.getString('device_mac');
        final uri = Uri.parse('$kBackendBaseUrl/api/media/files').replace(queryParameters: {
          if (_deviceMac != null && _deviceMac!.isNotEmpty) 'device_mac': _deviceMac!,
        });
        final resp =
          await _api.get(uri).timeout(
        const Duration(seconds: 10),
      );
      if (resp.statusCode == 200) {
        final data = json.decode(resp.body) as Map<String, dynamic>;
        final list = data['files'] as List<dynamic>? ?? [];
        setState(() {
          _files = list
              .whereType<Map<String, dynamic>>()
              .map(_MediaFile.fromJson)
              .toList(growable: false);
        });
      }
    } catch (_) {
      // ignore
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _pickAndUpload() async {
    final result = await FilePicker.platform.pickFiles(allowMultiple: true, withData: true);
    if (result == null || result.files.isEmpty) return;
    if (!_authed) {
      setState(() { _authError = 'Please sign in to upload.'; });
      return;
    }

    for (final file in result.files) {
      final uri = Uri.parse('$kBackendBaseUrl/api/media/upload');
      final request = http.MultipartRequest('POST', uri)
        ..fields['target'] = 'media';
      final prefs = await SharedPreferences.getInstance();
      final mac = prefs.getString('device_mac');
      if (mac != null && mac.isNotEmpty) {
        request.fields['device_mac'] = mac;
      }

      // On Web/mobile, path is null; use bytes. On mobile/desktop apps, use fromPath.
      if (kIsWeb || file.path == null) {
        final bytes = file.bytes;
        if (bytes == null) continue;
        request.files.add(http.MultipartFile.fromBytes('file', bytes, filename: file.name));
      } else {
        request.files.add(await http.MultipartFile.fromPath('file', file.path!));
      }

      try {
        final cookie = await _CookieStore.get();
        if (cookie != null && cookie.isNotEmpty) {
          request.headers['Cookie'] = cookie;
        }
        await request.send().timeout(const Duration(seconds: 30));
      } catch (_) {
        // ignore individual failures, continue others
      }
    }

    await _refresh();
  }

  Future<void> _deleteFile(_MediaFile file) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete file'),
        content: Text('Delete ${file.name}?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (ok != true) return;

    try {
        final prefs = await SharedPreferences.getInstance();
        final mac = prefs.getString('device_mac');
        final resp = await _api
          .post(Uri.parse('$kBackendBaseUrl/api/media/delete'),
              headers: {'Content-Type': 'application/json'},
              body: json.encode({'filename': file.name, if (mac != null && mac.isNotEmpty) 'device_mac': mac}))
          .timeout(const Duration(seconds: 10));
      if (resp.statusCode == 200) {
        _refresh();
      }
    } catch (_) {
      // ignore
    }
  }

  Future<void> _logout() async {
    try {
      final resp = await _api.post(Uri.parse('$kBackendBaseUrl/api/auth/logout')).timeout(const Duration(seconds: 10));
      if (resp.statusCode == 200) {
        await _CookieStore.set(null);
        setState(() {
          _authed = false;
          _files = const [];
          _deviceMac = null;
        });
      } else {
        // no-op
      }
    } catch (e) {
      // no-op
    }
  }

  // Account management moved to SettingsPage; inline handlers removed.

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('SSSNL Media Manager'),
        actions: [
          if (_authed)
            IconButton(
              icon: const Icon(Icons.settings),
              onPressed: () {
                Navigator.of(context).push(MaterialPageRoute(builder: (_) => const SettingsPage())).then((_) => _refresh());
              },
            ),
        ],
      ),
      body: Column(
        children: [
          if (!_authed) Padding(
            padding: const EdgeInsets.all(16),
            child: Card(
              color: const Color(0xFF020617),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text('Sign in or Sign up', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 12),
                    TextField(controller: _userCtrl, decoration: const InputDecoration(labelText: 'Username')),
                    const SizedBox(height: 8),
                    TextField(controller: _passCtrl, decoration: const InputDecoration(labelText: 'Password'), obscureText: true),
                    const SizedBox(height: 12),
                    Row(children: [
                      ElevatedButton(onPressed: _authLoading ? null : _login, child: const Text('Sign In')),
                      const SizedBox(width: 12),
                      OutlinedButton(onPressed: _authLoading ? null : _signup, child: const Text('Sign Up')),
                      if (_authLoading) ...[
                        const SizedBox(width: 12),
                        const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
                      ]
                    ]),
                    if (_authError != null) ...[
                      const SizedBox(height: 8),
                      Text(_authError!, style: const TextStyle(color: Colors.redAccent, fontSize: 12)),
                    ]
                  ],
                ),
              ),
            ),
          ),
          if (_authed) Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                ElevatedButton.icon(
                  onPressed: _pickAndUpload,
                  icon: const Icon(Icons.upload_file),
                  label: const Text('Upload'),
                ),
                const SizedBox(width: 12),
                OutlinedButton.icon(
                  onPressed: _refresh,
                  icon: const Icon(Icons.refresh),
                  label: const Text('Refresh'),
                ),
                const SizedBox(width: 12),
                OutlinedButton.icon(
                  onPressed: _logout,
                  icon: const Icon(Icons.logout),
                  label: const Text('Logout'),
                ),
                if (_loading) ...[
                  const SizedBox(width: 12),
                  const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                ],
              ],
            ),
          ),
          // Settings moved to separate page; no inline settings card.
          Expanded(
            child: !_authed
                ? const Center(child: Text('Please sign in to view your media'))
                : _files.isEmpty
                    ? const Center(child: Text('No media files found'))
                    : GridView.builder(
                    padding: const EdgeInsets.all(12),
                    gridDelegate:
                        const SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: 3,
                      mainAxisSpacing: 12,
                      crossAxisSpacing: 12,
                      childAspectRatio: 4 / 3,
                    ),
                    itemCount: _files.length,
                    itemBuilder: (ctx, index) {
                      final f = _files[index];
                      return Card(
                        color: const Color(0xFF020617),
                        child: Column(
                          children: [
                            Expanded(
                              child: f.type == 'image'
                                  ? Image.network(
                                      '$kBackendBaseUrl${f.url}',
                                      fit: BoxFit.cover,
                                      headers: _CookieStore.peekHeader(),
                                      errorBuilder: (_, __, ___) => const Icon(
                                        Icons.broken_image,
                                        color: Colors.white54,
                                      ),
                                    )
                                  : Icon(
                                      Icons.videocam,
                                      size: 48,
                                      color: Colors.blueGrey[200],
                                    ),
                            ),
                            Padding(
                              padding: const EdgeInsets.all(8),
                              child: Row(
                                children: [
                                  Expanded(
                                    child: Text(
                                      f.name,
                                      maxLines: 2,
                                      overflow: TextOverflow.ellipsis,
                                      style: const TextStyle(fontSize: 11),
                                    ),
                                  ),
                                  IconButton(
                                    onPressed: () => _deleteFile(f),
                                    icon: const Icon(Icons.delete_outline,
                                        size: 18),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}

class _DevControlsPage extends StatefulWidget {
  const _DevControlsPage();

  @override
  State<_DevControlsPage> createState() => _DevControlsPageState();
}

class _DevControlsPageState extends State<_DevControlsPage> {
  bool _sending = false;
  String? _lastMessage;
  final _tempCtrl = TextEditingController(text: '25.0');
  final _humCtrl = TextEditingController(text: '55.0');
  // Admin user management
  List<Map<String, dynamic>> _users = const [];
  final _newUserCtrl = TextEditingController();
  final _newPassCtrl = TextEditingController();
  String _newRole = 'user';
  // Change dev credentials
  final _devNewPassCtrl = TextEditingController();

  Future<void> _call(String path, Map<String, dynamic> body) async {
    setState(() {
      _sending = true;
      _lastMessage = null;
    });
    try {
      final resp = await _api
          .post(
            Uri.parse('$kBackendBaseUrl$path'),
            headers: {'Content-Type': 'application/json'},
            body: json.encode(body),
          )
          .timeout(const Duration(seconds: 10));
      setState(() {
        _lastMessage = '[$path] status ${resp.statusCode}: ${resp.body}';
      });
    } catch (e) {
      setState(() {
        _lastMessage = '[$path] error: $e';
      });
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _refreshUsers() async {
    try {
      final resp = await _api.get(Uri.parse('$kBackendBaseUrl/api/admin/users')).timeout(const Duration(seconds: 10));
      if (resp.statusCode == 200) {
        final data = json.decode(resp.body) as Map<String, dynamic>;
        setState(() { _users = (data['users'] as List).cast<Map<String, dynamic>>(); });
      }
    } catch (_) {}
  }

  Future<void> _addUser() async {
    try {
      final resp = await _api.post(
        Uri.parse('$kBackendBaseUrl/api/admin/users'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'username': _newUserCtrl.text.trim(), 'password': _newPassCtrl.text, 'role': _newRole}),
      ).timeout(const Duration(seconds: 10));
      if (resp.statusCode == 200) {
        _newUserCtrl.clear();
        _newPassCtrl.clear();
        await _refreshUsers();
      }
    } catch (_) {}
  }

  Future<void> _deleteUser(String username) async {
    try {
      final resp = await _api.delete(Uri.parse('$kBackendBaseUrl/api/admin/users/$username')).timeout(const Duration(seconds: 10));
      if (resp.statusCode == 200) {
        await _refreshUsers();
      }
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('SSSNL Dev Controls')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Developer Controls',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 12),
            const Text(
              'These controls only affect the mock overrides when running on '
              'your Ubuntu desktop. On the Pi, just don\'t use them and the '
              'real sensors will drive the dashboard.',
            ),
            const SizedBox(height: 20),
            const Text('Motion override'),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                ElevatedButton(
                  onPressed: _sending
                      ? null
                      : () => _call('/mock-motion', {'active': true}),
                  child: const Text('Motion ON'),
                ),
                ElevatedButton(
                  onPressed: _sending
                      ? null
                      : () => _call('/mock-motion', {'active': false}),
                  child: const Text('Motion OFF'),
                ),
                OutlinedButton(
                  onPressed: _sending
                      ? null
                      : () => _call('/mock-motion/clear', {}),
                  child: const Text('Clear override'),
                ),
              ],
            ),
            const SizedBox(height: 24),
            const Text('DHT override'),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _tempCtrl,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'Temp (°C)',
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextField(
                    controller: _humCtrl,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'Humidity (%)',
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                ElevatedButton(
                  onPressed: _sending
                      ? null
                      : () => _call('/mock-dht', {
                            'temp': _tempCtrl.text,
                            'hum': _humCtrl.text,
                          }),
                  child: const Text('Apply DHT override'),
                ),
                OutlinedButton(
                  onPressed: _sending
                      ? null
                      : () => _call('/mock-dht/clear', {}),
                  child: const Text('Clear DHT override'),
                ),
              ],
            ),
            const SizedBox(height: 24),
            const Divider(),
            const Text('User Management (Admin)', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            Row(children: [
              Expanded(child: TextField(controller: _newUserCtrl, decoration: const InputDecoration(labelText: 'Username'))),
              const SizedBox(width: 8),
              Expanded(child: TextField(controller: _newPassCtrl, decoration: const InputDecoration(labelText: 'Password'), obscureText: true)),
              const SizedBox(width: 8),
              DropdownButton<String>(
                value: _newRole,
                items: const [DropdownMenuItem(value: 'user', child: Text('user')), DropdownMenuItem(value: 'admin', child: Text('admin'))],
                onChanged: (v) => setState(() { if (v != null) _newRole = v; }),
              ),
              const SizedBox(width: 8),
              ElevatedButton(onPressed: _addUser, child: const Text('Add')),
              const SizedBox(width: 8),
              OutlinedButton(onPressed: _refreshUsers, child: const Text('Refresh')),
            ]),
            const SizedBox(height: 12),
            for (final u in _users) ListTile(
              title: Text('${u['username']}'),
              subtitle: Text('role: ${u['role']}'),
              trailing: IconButton(onPressed: () => _deleteUser('${u['username']}'), icon: const Icon(Icons.delete_outline)),
            ),
            const Divider(),
            const Text('Change Dev Password', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            Row(children: [
              Expanded(child: TextField(controller: _devNewPassCtrl, decoration: const InputDecoration(labelText: 'New Password'), obscureText: true)),
              const SizedBox(width: 8),
              ElevatedButton(
                onPressed: () async {
                  try {
                    final resp = await _api.post(
                      Uri.parse('$kBackendBaseUrl/api/admin/change_password'),
                      headers: {'Content-Type': 'application/json'},
                      body: json.encode({'username': 'dev', 'password': _devNewPassCtrl.text}),
                    ).timeout(const Duration(seconds: 10));
                    setState(() { _lastMessage = resp.statusCode == 200 ? 'Dev password updated' : 'Update failed (${resp.statusCode})'; });
                    _devNewPassCtrl.clear();
                  } catch (e) {
                    setState(() { _lastMessage = 'Update error: $e'; });
                  }
                },
                child: const Text('Update'),
              ),
            ]),
            if (_sending) const LinearProgressIndicator(),
            if (_lastMessage != null) ...[
              const SizedBox(height: 12),
              Text(
                _lastMessage!,
                style: const TextStyle(fontSize: 12, color: Colors.white70),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
