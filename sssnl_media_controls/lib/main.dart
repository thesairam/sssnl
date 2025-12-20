import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

void main() {
  runApp(const MediaControlsApp());
}

/// Backend base URL: use the current origin when running as Flutter Web.
/// This avoids localhost issues on mobile and ensures same-origin requests.
final String kBackendBaseUrl = Uri.base.origin;

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
      // Split correctly: /dev -> controls-only (with login); /media -> media-only
      home: isDev ? const _LoginScreen() : const _MediaManagerPage(),
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
    http
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
  // User self-management controllers
  final _oldPassCtrl = TextEditingController();
  final _newPassCtrl = TextEditingController();
  final _newUsernameCtrl = TextEditingController();
  final _verifyPassCtrl = TextEditingController();
  String? _userMsg;

  @override
  void initState() {
    super.initState();
    _checkAuth().then((_) { if (_authed) _refresh(); });
  }

  Future<void> _checkAuth() async {
    setState(() { _authLoading = true; _authError = null; });
    try {
      final resp = await http.get(Uri.parse('$kBackendBaseUrl/api/auth/me')).timeout(const Duration(seconds: 10));
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
      final resp = await http.post(
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
      final resp = await http.post(
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
        final resp =
          await http.get(Uri.parse('$kBackendBaseUrl/api/media/files')).timeout(
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

      // On Web/mobile, path is null; use bytes. On mobile/desktop apps, use fromPath.
      if (kIsWeb || file.path == null) {
        final bytes = file.bytes;
        if (bytes == null) continue;
        request.files.add(http.MultipartFile.fromBytes('file', bytes, filename: file.name));
      } else {
        request.files.add(await http.MultipartFile.fromPath('file', file.path!));
      }

      try {
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
        final resp = await http
          .post(Uri.parse('$kBackendBaseUrl/api/media/delete'),
              headers: {'Content-Type': 'application/json'},
              body: json.encode({'filename': file.name}))
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
      final resp = await http.post(Uri.parse('$kBackendBaseUrl/api/auth/logout')).timeout(const Duration(seconds: 10));
      if (resp.statusCode == 200) {
        setState(() {
          _authed = false;
          _files = const [];
          _userMsg = 'Signed out.';
        });
      } else {
        setState(() { _userMsg = 'Logout failed (${resp.statusCode})'; });
      }
    } catch (e) {
      setState(() { _userMsg = 'Logout error: $e'; });
    }
  }

  Future<void> _changePassword() async {
    setState(() { _userMsg = null; });
    try {
      final resp = await http.post(
        Uri.parse('$kBackendBaseUrl/api/user/change_password'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'old_password': _oldPassCtrl.text, 'new_password': _newPassCtrl.text}),
      ).timeout(const Duration(seconds: 10));
      setState(() {
        _userMsg = resp.statusCode == 200 ? 'Password updated.' : 'Update failed (${resp.statusCode})';
      });
      if (resp.statusCode == 200) {
        _oldPassCtrl.clear();
        _newPassCtrl.clear();
      }
    } catch (e) {
      setState(() { _userMsg = 'Update error: $e'; });
    }
  }

  Future<void> _changeUsername() async {
    setState(() { _userMsg = null; });
    try {
      final resp = await http.post(
        Uri.parse('$kBackendBaseUrl/api/user/change_username'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'new_username': _newUsernameCtrl.text.trim().toLowerCase(), 'password': _verifyPassCtrl.text}),
      ).timeout(const Duration(seconds: 10));
      if (resp.statusCode == 200) {
        setState(() { _userMsg = 'Username updated.'; });
        _newUsernameCtrl.clear();
        _verifyPassCtrl.clear();
        await _refresh();
      } else if (resp.statusCode == 409) {
        setState(() { _userMsg = 'Username already exists.'; });
      } else {
        setState(() { _userMsg = 'Update failed (${resp.statusCode})'; });
      }
    } catch (e) {
      setState(() { _userMsg = 'Update error: $e'; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('SSSNL Media Manager')),
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
          if (_authed) Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Card(
              color: const Color(0xFF020617),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text('User Settings', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 8),
                    Row(children: [
                      Expanded(child: TextField(controller: _oldPassCtrl, decoration: const InputDecoration(labelText: 'Current Password'), obscureText: true)),
                      const SizedBox(width: 8),
                      Expanded(child: TextField(controller: _newPassCtrl, decoration: const InputDecoration(labelText: 'New Password'), obscureText: true)),
                      const SizedBox(width: 8),
                      ElevatedButton(onPressed: _changePassword, child: const Text('Change Password')),
                    ]),
                    const SizedBox(height: 8),
                    Row(children: [
                      Expanded(child: TextField(controller: _newUsernameCtrl, decoration: const InputDecoration(labelText: 'New Username'))),
                      const SizedBox(width: 8),
                      Expanded(child: TextField(controller: _verifyPassCtrl, decoration: const InputDecoration(labelText: 'Password (verify)'), obscureText: true)),
                      const SizedBox(width: 8),
                      ElevatedButton(onPressed: _changeUsername, child: const Text('Change Username')),
                    ]),
                    if (_userMsg != null) ...[
                      const SizedBox(height: 8),
                      Text(_userMsg!, style: const TextStyle(fontSize: 12, color: Colors.white70)),
                    ],
                  ],
                ),
              ),
            ),
          ),
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
      final resp = await http
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
      final resp = await http.get(Uri.parse('$kBackendBaseUrl/api/admin/users')).timeout(const Duration(seconds: 10));
      if (resp.statusCode == 200) {
        final data = json.decode(resp.body) as Map<String, dynamic>;
        setState(() { _users = (data['users'] as List).cast<Map<String, dynamic>>(); });
      }
    } catch (_) {}
  }

  Future<void> _addUser() async {
    try {
      final resp = await http.post(
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
      final resp = await http.delete(Uri.parse('$kBackendBaseUrl/api/admin/users/$username')).timeout(const Duration(seconds: 10));
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
                    final resp = await http.post(
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
