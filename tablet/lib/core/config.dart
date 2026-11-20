import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// A qué backend de ATLAS se conecta la tablet y cómo confía en él.
class ServerConfig {
  const ServerConfig({required this.baseUrl, this.fingerprint, this.password = ''});

  /// Ej. https://192.168.0.7:8000 (sin barra final).
  final String baseUrl;

  /// SHA-256 del certificado del backend (autofirmado). La app solo acepta
  /// ese certificado exacto: sin esto, cualquiera en la WiFi podría hacerse
  /// pasar por ATLAS. Null para http plano.
  final String? fingerprint;

  /// Contraseña de ATLAS (ATLAS_PASSWORD). Vacía si el backend no pide login.
  final String password;

  Uri get uri => Uri.parse(baseUrl);
}

/// Preferencias de la app en la tablet.
class AppPrefs {
  AppPrefs(this._prefs);

  final SharedPreferences _prefs;
  static const _secure = FlutterSecureStorage();

  static const _kUrl = 'server_url';
  static const _kFingerprint = 'server_fingerprint';
  static const _kPassword = 'server_password';
  static const _kSpeak = 'speak_replies';
  static const _kHandsFree = 'hands_free';
  static const _kSensitivity = 'mic_sensitivity';
  static const _kFollowUp = 'follow_up';
  static const _kWakeSound = 'wake_sound';
  static const _kHandsFreeConsent = 'hands_free_consent';

  static Future<AppPrefs> load() async => AppPrefs(await SharedPreferences.getInstance());

  Future<ServerConfig?> server() async {
    final url = _prefs.getString(_kUrl);
    if (url == null || url.isEmpty) return null;
    return ServerConfig(
      baseUrl: url,
      fingerprint: _prefs.getString(_kFingerprint),
      password: await _secure.read(key: _kPassword) ?? '',
    );
  }

  Future<void> saveServer(ServerConfig config) async {
    await _prefs.setString(_kUrl, config.baseUrl);
    if (config.fingerprint == null) {
      await _prefs.remove(_kFingerprint);
    } else {
      await _prefs.setString(_kFingerprint, config.fingerprint!);
    }
    await _secure.write(key: _kPassword, value: config.password);
  }

  Future<void> forgetServer() async {
    await _prefs.remove(_kUrl);
    await _prefs.remove(_kFingerprint);
    await _secure.delete(key: _kPassword);
  }

  /// Leer en voz alta todas las respuestas de ATLAS (por defecto sí).
  bool get speakReplies => _prefs.getBool(_kSpeak) ?? true;
  set speakReplies(bool value) => _prefs.setBool(_kSpeak, value);

  /// "Escuchar «Atlas»": la tablet espera la palabra de activación.
  bool get handsFree => _prefs.getBool(_kHandsFree) ?? false;
  set handsFree(bool value) => _prefs.setBool(_kHandsFree, value);

  /// Ya aceptó el aviso de privacidad del micrófono abierto.
  bool get handsFreeConsent => _prefs.getBool(_kHandsFreeConsent) ?? false;
  set handsFreeConsent(bool value) => _prefs.setBool(_kHandsFreeConsent, value);

  /// 0 (estricta, ignora voces lejanas) … 1 (capta voz baja).
  double get micSensitivity => _prefs.getDouble(_kSensitivity) ?? 0.5;
  set micSensitivity(double value) => _prefs.setDouble(_kSensitivity, value);

  /// Tras una respuesta, unos segundos para seguir hablando sin decir "Atlas".
  bool get followUp => _prefs.getBool(_kFollowUp) ?? true;
  set followUp(bool value) => _prefs.setBool(_kFollowUp, value);

  /// Sonido de aviso al oír "Atlas".
  bool get wakeSound => _prefs.getBool(_kWakeSound) ?? true;
  set wakeSound(bool value) => _prefs.setBool(_kWakeSound, value);
}
