import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;
import 'package:http/io_client.dart';

import 'config.dart';
import 'models.dart';
import 'models_extra.dart';

export 'models_extra.dart';

/// Error apto para mostrar al usuario.
class AtlasException implements Exception {
  AtlasException(this.message, {this.status});

  final String message;
  final int? status;

  @override
  String toString() => message;
}

/// Cliente del backend de ATLAS (la misma API que usan el escritorio y la web).
class AtlasApi {
  AtlasApi(this.config) : _client = IOClient(_httpClient(config));

  final ServerConfig config;
  final http.Client _client;
  String? _token;

  /// El backend usa un certificado autofirmado: en vez de rechazarlo, se acepta
  /// solo si su huella es la que el usuario confirmó al conectar la tablet.
  static HttpClient _httpClient(ServerConfig config) {
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 8);
    client.badCertificateCallback =
        (cert, host, port) => config.fingerprint != null && fingerprintOf(cert) == config.fingerprint;
    return client;
  }

  static String fingerprintOf(X509Certificate cert) => sha256.convert(cert.der).toString();

  /// "9e29 2631 …" — más fácil de comparar a ojo.
  static String prettyFingerprint(String hex) =>
      [for (var i = 0; i < hex.length; i += 4) hex.substring(i, (i + 4).clamp(0, hex.length))].join(' ').toUpperCase();

  /// Huella del certificado autofirmado que presenta el servidor, para que el
  /// usuario la confirme. null si es http o si el certificado es público y
  /// válido (ej. atlas.sirinetrd.com vía Cloudflare): ahí basta la verificación
  /// normal del sistema, y la huella de Cloudflare cambia cada tanto.
  static Future<String?> probeFingerprint(Uri uri) async {
    if (uri.scheme != 'https') return null;
    X509Certificate? untrusted;
    final socket = await SecureSocket.connect(
      uri.host,
      uri.port,
      timeout: const Duration(seconds: 6),
      onBadCertificate: (cert) {
        untrusted = cert;
        return true;
      },
    );
    socket.destroy();
    return untrusted == null ? null : fingerprintOf(untrusted!);
  }

  void close() => _client.close();

  Uri _url(String path, [Map<String, String>? query]) {
    final base = config.uri;
    return base.replace(path: '${base.path}/api/v1$path', queryParameters: query?.isEmpty ?? true ? null : query);
  }

  Map<String, String> get _auth => _token == null ? {} : {'Authorization': 'Bearer $_token'};

  Future<void> login() async {
    if (config.password.isEmpty) return;
    final response = await _client
        .post(_url('/auth/login'), headers: {'Content-Type': 'application/json'}, body: jsonEncode({'password': config.password}))
        .timeout(const Duration(seconds: 15));
    if (response.statusCode == 401) throw AtlasException('Contraseña de ATLAS incorrecta.', status: 401);
    _check(response);
    _token = (jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>)['access_token'] as String?;
  }

  /// Envía una petición; si la sesión venció, inicia sesión y reintenta una vez.
  Future<http.Response> _send(
    String method,
    String path, {
    Object? body,
    Map<String, String>? query,
    Duration timeout = const Duration(seconds: 20),
  }) async {
    Future<http.Response> attempt() {
      final request = http.Request(method, _url(path, query))..headers.addAll(_auth);
      if (body != null) {
        request.headers['Content-Type'] = 'application/json';
        request.bodyBytes = utf8.encode(jsonEncode(body));
      }
      return _client.send(request).then(http.Response.fromStream).timeout(timeout);
    }

    try {
      if (_token == null && config.password.isNotEmpty) await login();
      var response = await attempt();
      if ((response.statusCode == 401 || response.statusCode == 403) && config.password.isNotEmpty) {
        _token = null;
        await login();
        response = await attempt();
      }
      _check(response);
      return response;
    } on AtlasException {
      rethrow;
    } on TimeoutException {
      throw AtlasException('ATLAS tardó demasiado en responder.');
    } on HandshakeException {
      throw AtlasException('El certificado del servidor cambió. Vuelve a conectar la tablet en Configuración.');
    } on SocketException {
      throw AtlasException('No pude conectar con ATLAS en ${config.baseUrl}. Revisa el internet de la tablet y que la PC con ATLAS esté encendida.');
    } on http.ClientException {
      throw AtlasException('No pude conectar con ATLAS en ${config.baseUrl}.');
    }
  }

  void _check(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) return;
    String? detail;
    try {
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      final raw = decoded is Map ? decoded['detail'] : null;
      detail = raw is String ? raw : (raw is List && raw.isNotEmpty ? '${(raw.first as Map)['msg']}' : null);
    } catch (_) {}
    if (response.statusCode == 401 || response.statusCode == 403) {
      throw AtlasException(detail ?? 'ATLAS pide contraseña. Configúrala en Configuración.', status: response.statusCode);
    }
    throw AtlasException(detail ?? 'ATLAS respondió con un error (HTTP ${response.statusCode}).', status: response.statusCode);
  }

  Future<dynamic> _json(String method, String path, {Object? body, Map<String, String>? query, Duration? timeout}) async {
    final response = await _send(method, path, body: body, query: query, timeout: timeout ?? const Duration(seconds: 20));
    return response.bodyBytes.isEmpty ? null : jsonDecode(utf8.decode(response.bodyBytes));
  }

  // --- Conexión ---------------------------------------------------------------

  Future<Map<String, dynamic>> health() async => await _json('GET', '/system/health') as Map<String, dynamic>;

  /// Comprueba que la sesión sirve para endpoints protegidos.
  Future<void> verifyAccess() => _json('GET', '/notifications', query: {'unread_only': 'true'});

  Future<Map<String, dynamic>> personality() async => await _json('GET', '/settings/personality') as Map<String, dynamic>;

  // --- Chat -------------------------------------------------------------------

  Future<ChatReply> chat(String message, {String? conversationId, List<ChatAttachment> attachments = const []}) async {
    final body = {
      'message': message,
      'conversation_id': ?conversationId,
      if (attachments.isNotEmpty) 'attachments': [for (final a in attachments) a.toJson()],
    };
    // Con imágenes, leer una factura y armar el Excel puede llevar un minuto.
    return ChatReply.fromJson(await _json('POST', '/chat', body: body, timeout: const Duration(minutes: 3)) as Map<String, dynamic>);
  }

  Future<ChatReply> confirm(String confirmationId, bool approve) async {
    final json = await _json('POST', '/chat/confirm',
        body: {'confirmation_id': confirmationId, 'approve': approve}, timeout: const Duration(minutes: 3)) as Map<String, dynamic>;
    return ChatReply.fromJson(json);
  }

  Future<Uint8List> downloadFile(String name) async =>
      (await _send('GET', '/files/${Uri.encodeComponent(name)}', timeout: const Duration(minutes: 1))).bodyBytes;

  // --- Voz --------------------------------------------------------------------

  /// `prompt` sesga a Whisper (ej. hacia la palabra "Atlas" en reposo).
  Future<String> transcribe(Uint8List wav, {String? prompt}) async {
    Future<http.Response> attempt() async {
      final request = http.MultipartRequest('POST', _url('/voice/transcribe', {'prompt': ?prompt}))
        ..headers.addAll(_auth)
        ..files.add(http.MultipartFile.fromBytes('audio', wav, filename: 'audio.wav'));
      return http.Response.fromStream(await _client.send(request)).timeout(const Duration(seconds: 60));
    }

    try {
      if (_token == null && config.password.isNotEmpty) await login();
      var response = await attempt();
      if (response.statusCode == 401 && config.password.isNotEmpty) {
        _token = null;
        await login();
        response = await attempt();
      }
      _check(response);
      return ((jsonDecode(utf8.decode(response.bodyBytes)) as Map)['text'] as String? ?? '').trim();
    } on SocketException {
      throw AtlasException('No pude conectar con ATLAS para transcribir.');
    } on TimeoutException {
      throw AtlasException('La transcripción tardó demasiado.');
    }
  }

  /// `voice`/`speed`: solo para escuchar una voz antes de elegirla.
  Future<Uint8List> speak(String text, {String? voice, double? speed}) async => (await _send('POST', '/voice/speak',
          body: {'text': text, 'voice': ?voice, 'speed': ?speed}, timeout: const Duration(seconds: 90)))
      .bodyBytes;

  Future<VoiceCatalog> voices() async => VoiceCatalog.fromJson(await _json('GET', '/voice/voices') as Map<String, dynamic>);

  /// Cambia la voz de ATLAS para todos los dispositivos (se guarda en el backend).
  Future<VoiceCatalog> chooseVoice(String voice, double speed) async =>
      VoiceCatalog.fromJson(await _json('PUT', '/voice/voice', body: {'voice': voice, 'speed': speed}) as Map<String, dynamic>);

  // --- PC ---------------------------------------------------------------------

  /// Nombres de las herramientas que tiene el backend (para mostrar solo las acciones posibles).
  Future<Set<String>> toolNames() async =>
      {for (final t in await _json('GET', '/tools') as List) (t as Map<String, dynamic>)['name'] as String};

  Future<PcStatus> systemStatus() async => PcStatus.fromJson(await _json('GET', '/system/status') as Map<String, dynamic>);

  Future<List<ActivityEntry>> activity({int limit = 30}) async => [
        for (final a in await _json('GET', '/system/activity', query: {'limit': '$limit'}) as List)
          ActivityEntry.fromJson(a as Map<String, dynamic>)
      ];

  // --- Paneles ----------------------------------------------------------------

  Future<Weather> weather() async => Weather.fromJson(await _json('GET', '/widgets/weather') as Map<String, dynamic>);

  Future<List<Headline>> news() async =>
      [for (final h in await _json('GET', '/widgets/news', query: {'limit': '6'}) as List) Headline.fromJson(h as Map<String, dynamic>)];

  Future<List<Reminder>> reminders() async =>
      [for (final r in await _json('GET', '/reminders') as List) Reminder.fromJson(r as Map<String, dynamic>)];

  Future<void> cancelReminder(int id) => _json('DELETE', '/reminders/$id');

  Future<List<AtlasNotification>> notifications() async => [
        for (final n in await _json('GET', '/notifications') as List)
          AtlasNotification.fromJson(n as Map<String, dynamic>)
      ];

  Future<void> markNotificationRead(int id) => _json('PATCH', '/notifications/$id/read');

  Future<List<Device>> devices() async =>
      [for (final d in await _json('GET', '/devices') as List) Device.fromJson(d as Map<String, dynamic>)];

  Future<List<Memory>> memories({String query = ''}) async {
    final json = query.trim().isEmpty
        ? await _json('GET', '/memory', query: {'limit': '100'})
        : await _json('GET', '/memory/search', query: {'q': query.trim()});
    return [for (final m in json as List) Memory.fromJson(m as Map<String, dynamic>)];
  }

  Future<void> addMemory(String content) => _json('POST', '/memory', body: {'content': content});

  Future<void> deleteMemory(int id) => _json('DELETE', '/memory/$id');
}
