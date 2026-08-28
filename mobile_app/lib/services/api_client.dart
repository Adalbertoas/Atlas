import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../models/device.dart';

/// Excepción para cualquier fallo de la API — mensaje ya listo para mostrar,
/// mismo criterio que el helper `api()` de dashboard/app.js (arma un
/// Error con el `detail` del backend cuando lo hay).
class ApiException implements Exception {
  final String message;
  ApiException(this.message);

  @override
  String toString() => message;
}

/// Un evento del streaming de /chat/stream — mismo shape que StreamOutEvent
/// del backend (app/core/orchestrator.py), ya deserializado.
class ChatStreamEvent {
  final String type; // "token" | "tool_call" | "confirmation" | "done"
  final String? text;
  final String? toolName;
  final String? toolDescription;
  final String? conversationId;
  final String? reply;
  final String? confirmationId;
  final String? confirmationDescription;

  ChatStreamEvent({
    required this.type,
    this.text,
    this.toolName,
    this.toolDescription,
    this.conversationId,
    this.reply,
    this.confirmationId,
    this.confirmationDescription,
  });

  factory ChatStreamEvent.fromSse(String eventType, Map<String, dynamic> data) {
    return ChatStreamEvent(
      type: eventType,
      text: data['text'] as String?,
      toolName: data['tool_name'] as String?,
      toolDescription: data['tool_description'] as String?,
      conversationId: data['conversation_id'] as String?,
      reply: data['reply'] as String?,
      confirmationId: data['confirmation_id'] as String?,
      confirmationDescription: data['confirmation_description'] as String?,
    );
  }
}

class ChatResult {
  final String? reply;
  final String conversationId;
  final bool requiresConfirmation;
  final String? confirmationId;
  final String? confirmationDescription;

  ChatResult({
    required this.reply,
    required this.conversationId,
    required this.requiresConfirmation,
    this.confirmationId,
    this.confirmationDescription,
  });

  factory ChatResult.fromJson(Map<String, dynamic> json) {
    return ChatResult(
      reply: json['reply'] as String?,
      conversationId: json['conversation_id'] as String,
      requiresConfirmation: json['requires_confirmation'] as bool? ?? false,
      confirmationId: json['confirmation_id'] as String?,
      confirmationDescription: json['confirmation_description'] as String?,
    );
  }
}

/// Cliente HTTP de la API de ATLAS. Guarda `baseUrl`/`token` en
/// SharedPreferences (mismo criterio que localStorage en dashboard/mobile:
/// persisten entre reinicios de la app, alcanza para un sistema personal de
/// un solo usuario).
class ApiClient {
  static const _baseUrlKey = 'atlas_base_url';
  static const _tokenKey = 'atlas_token';

  String? _baseUrl;
  String? _token;

  /// HomeScreen lo setea para volver al login apenas un request cualquiera
  /// devuelve 401 (token expirado, o revocado desde otro dispositivo por
  /// /auth/logout) — mismo criterio que el `api()` de dashboard/app.js:
  /// sin esto la app queda mostrando errores repetidos en vez de pedir que
  /// se loguee de nuevo.
  VoidCallback? onSessionExpired;

  bool get isLoggedIn => _token != null;
  String? get baseUrl => _baseUrl;

  /// Limpia el token local (no revoca nada server-side — para eso está
  /// logout()) y avisa a quien esté escuchando. Se llama ante cualquier 401
  /// que no sea el propio intento de login.
  Future<void> _handleUnauthorized() async {
    _token = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
    onSessionExpired?.call();
  }

  Future<void> loadFromStorage() async {
    final prefs = await SharedPreferences.getInstance();
    _baseUrl = prefs.getString(_baseUrlKey);
    _token = prefs.getString(_tokenKey);
  }

  Future<void> setBaseUrl(String url) async {
    // Sin barra final: se concatena directo con paths que empiezan en "/".
    _baseUrl = url.endsWith('/') ? url.substring(0, url.length - 1) : url;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_baseUrlKey, _baseUrl!);
  }

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  Map<String, String> _headers({bool json = true}) {
    final headers = <String, String>{};
    if (_token != null) headers['Authorization'] = 'Bearer $_token';
    if (json) headers['Content-Type'] = 'application/json';
    return headers;
  }

  /// Extrae el `detail` del body de error, con el mismo fallback que
  /// dashboard/app.js: si no hay JSON, se usa el texto de estado HTTP.
  Future<String> _errorDetail(http.Response response) async {
    try {
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      return body['detail'] as String? ?? response.reasonPhrase ?? 'Error desconocido';
    } catch (_) {
      return response.reasonPhrase ?? 'Error desconocido';
    }
  }

  Future<void> login(String password) async {
    final response = await http.post(
      _uri('/api/v1/auth/login'),
      headers: _headers(),
      body: jsonEncode({'password': password}),
    );
    if (response.statusCode != 200) {
      throw ApiException(await _errorDetail(response));
    }
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    _token = body['access_token'] as String;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, _token!);
  }

  Future<void> logout() async {
    // Revoca el token server-side antes de descartarlo (POST /auth/logout,
    // ver app/security/auth.py) — best-effort, mismo criterio que
    // dashboard/app.js: si falla (sin red), el logout local sigue igual.
    if (_token != null) {
      try {
        await http.post(_uri('/api/v1/auth/logout'), headers: _headers(json: false));
      } catch (_) {
        // no bloquea el logout local
      }
    }
    _token = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
  }

  /// Ante un 401 en cualquier request autenticado (token expirado, o
  /// revocado desde otro dispositivo por /auth/logout — ver
  /// backend/app/security/auth.py) limpia el token local y avisa a
  /// onSessionExpired antes de lanzar, para que la UI pueda mandar al
  /// usuario de vuelta al login en vez de mostrar un error genérico.
  Future<void> _checkAuth(http.BaseResponse response) async {
    if (response.statusCode == 401) {
      await _handleUnauthorized();
      throw ApiException('Sesión expirada, iniciá sesión de nuevo.');
    }
  }

  Future<ChatResult> sendChat(String message, {String? conversationId}) async {
    final response = await http.post(
      _uri('/api/v1/chat'),
      headers: _headers(),
      body: jsonEncode({'message': message, 'conversation_id': conversationId}),
    );
    await _checkAuth(response);
    if (response.statusCode != 200) {
      throw ApiException(await _errorDetail(response));
    }
    return ChatResult.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<ChatResult> confirmAction(String confirmationId, bool approve) async {
    final response = await http.post(
      _uri('/api/v1/chat/confirm'),
      headers: _headers(),
      body: jsonEncode({'confirmation_id': confirmationId, 'approve': approve}),
    );
    await _checkAuth(response);
    if (response.statusCode != 200) {
      throw ApiException(await _errorDetail(response));
    }
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    // /chat/confirm devuelve ConfirmResponse (solo `reply`), no un
    // ChatResult completo — se envuelve para que el caller use la misma
    // forma que sendChat().
    return ChatResult(reply: body['reply'] as String?, conversationId: '', requiresConfirmation: false);
  }

  /// Streaming de /chat/stream (Server-Sent Events) — mismo protocolo que
  /// parsea dashboard/app.js: `"event: <tipo>\ndata: <json>\n\n"` por evento.
  /// http.Client().send() da acceso al StreamedResponse antes de que
  /// termine de llegar, a diferencia de http.post() que espera el body
  /// completo — necesario para que los tokens aparezcan en vivo.
  Stream<ChatStreamEvent> sendChatStream(String message, {String? conversationId}) async* {
    final request = http.Request('POST', _uri('/api/v1/chat/stream'))
      ..headers.addAll(_headers())
      ..body = jsonEncode({'message': message, 'conversation_id': conversationId});

    final client = http.Client();
    try {
      final response = await client.send(request);
      if (response.statusCode == 401) {
        await response.stream.drain<void>().catchError((_) {});
        await _handleUnauthorized();
        throw ApiException('Sesión expirada, iniciá sesión de nuevo.');
      }
      if (response.statusCode != 200) {
        final body = await response.stream.bytesToString();
        String detail;
        try {
          detail = (jsonDecode(body) as Map<String, dynamic>)['detail'] as String? ?? 'Error desconocido';
        } catch (_) {
          detail = 'Error desconocido';
        }
        throw ApiException(detail);
      }

      var buffer = '';
      await for (final chunk in response.stream.transform(utf8.decoder)) {
        buffer += chunk;
        var separatorIndex = buffer.indexOf('\n\n');
        while (separatorIndex != -1) {
          final rawEvent = buffer.substring(0, separatorIndex);
          buffer = buffer.substring(separatorIndex + 2);

          final lines = rawEvent.split('\n');
          if (lines.length >= 2) {
            final eventType = lines[0].replaceFirst(RegExp(r'^event:\s*'), '');
            final dataLine = lines[1].replaceFirst(RegExp(r'^data:\s*'), '');
            final data = dataLine.isEmpty ? <String, dynamic>{} : jsonDecode(dataLine) as Map<String, dynamic>;
            yield ChatStreamEvent.fromSse(eventType, data);
          }
          separatorIndex = buffer.indexOf('\n\n');
        }
      }
    } finally {
      client.close();
    }
  }

  Future<List<Device>> listDevices() async {
    final response = await http.get(_uri('/api/v1/devices'), headers: _headers(json: false));
    await _checkAuth(response);
    if (response.statusCode != 200) {
      throw ApiException(await _errorDetail(response));
    }
    final list = jsonDecode(response.body) as List;
    return list.map((e) => Device.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<bool> checkHealth(String candidateBaseUrl) async {
    try {
      final response = await http
          .get(Uri.parse('$candidateBaseUrl/api/v1/system/health'))
          .timeout(const Duration(seconds: 2));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }
}
