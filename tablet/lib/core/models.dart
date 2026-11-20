import 'dart:convert';
import 'dart:typed_data';

/// Horas del backend: UTC, a veces sin zona ("2026-11-18T18:21:24"). Se pasan a hora local.
DateTime? parseServerTime(Object? raw) {
  final text = raw?.toString() ?? '';
  if (text.isEmpty) return null;
  final hasZone = text.endsWith('Z') || RegExp(r'[+-]\d\d:?\d\d$').hasMatch(text);
  return DateTime.tryParse(hasZone ? text : '${text}Z')?.toLocal();
}

/// Imagen o PDF que el usuario adjunta a un mensaje.
class ChatAttachment {
  ChatAttachment({required this.name, required this.mimeType, required this.bytes});

  final String name;
  final String mimeType;
  final Uint8List bytes;

  bool get isImage => mimeType.startsWith('image/');

  Map<String, dynamic> toJson() => {'name': name, 'mime_type': mimeType, 'data': base64Encode(bytes)};
}

/// Imagen que devolvió una tool (ej. un mapa).
class ChatImage {
  ChatImage(this.mimeType, this.bytes);

  final String mimeType;
  final Uint8List bytes;

  factory ChatImage.fromJson(Map<String, dynamic> json) =>
      ChatImage(json['mime_type'] as String? ?? 'image/png', base64Decode(json['data'] as String? ?? ''));
}

/// Archivo que generó ATLAS (ej. un Excel); se baja de GET /files/{name}.
class GeneratedFile {
  GeneratedFile({required this.name, required this.mimeType, required this.size});

  final String name;
  final String mimeType;
  final int size;

  factory GeneratedFile.fromJson(Map<String, dynamic> json) => GeneratedFile(
        name: json['name'] as String? ?? 'archivo',
        mimeType: json['mime_type'] as String? ?? 'application/octet-stream',
        size: (json['size'] as num?)?.toInt() ?? 0,
      );

  bool get isSpreadsheet => name.toLowerCase().endsWith('.xlsx');

  String get sizeLabel => size < 1024
      ? '$size B'
      : size < 1024 * 1024
          ? '${(size / 1024).round()} KB'
          : '${(size / 1024 / 1024).toStringAsFixed(1)} MB';
}

/// Respuesta de POST /chat o /chat/confirm.
class ChatReply {
  ChatReply({
    required this.text,
    this.conversationId,
    this.confirmationId,
    this.confirmationDescription,
    this.images = const [],
    this.files = const [],
  });

  final String text;
  final String? conversationId;
  final String? confirmationId;
  final String? confirmationDescription;
  final List<ChatImage> images;
  final List<GeneratedFile> files;

  bool get needsConfirmation => confirmationId != null;

  factory ChatReply.fromJson(Map<String, dynamic> json) => ChatReply(
        text: json['reply'] as String? ?? '',
        conversationId: json['conversation_id'] as String?,
        confirmationId: json['requires_confirmation'] == true ? json['confirmation_id'] as String? : null,
        confirmationDescription: json['confirmation_description'] as String?,
        images: [for (final i in (json['images'] as List? ?? [])) ChatImage.fromJson(i as Map<String, dynamic>)],
        files: [for (final f in (json['files'] as List? ?? [])) GeneratedFile.fromJson(f as Map<String, dynamic>)],
      );
}

/// Un mensaje en pantalla.
class ChatMessage {
  ChatMessage.user(this.text, {this.attachments = const [], this.spoken = false})
      : fromUser = true,
        images = const [],
        files = const [],
        isError = false;

  ChatMessage.assistant(ChatReply reply)
      : fromUser = false,
        spoken = false,
        text = reply.text,
        attachments = const [],
        images = reply.images,
        files = reply.files,
        confirmationId = reply.confirmationId,
        confirmationDescription = reply.confirmationDescription,
        isError = false;

  ChatMessage.error(this.text)
      : fromUser = false,
        spoken = false,
        attachments = const [],
        images = const [],
        files = const [],
        isError = true;

  final bool fromUser;
  String text;
  final List<ChatAttachment> attachments;
  final List<ChatImage> images;
  final List<GeneratedFile> files;
  String? confirmationId;
  String? confirmationDescription;
  final bool isError;

  /// El usuario lo dijo por voz (se marca con un micrófono en la burbuja).
  final bool spoken;
}

class Reminder {
  Reminder(this.id, this.message, this.description, this.dueAt);

  final int id;
  final String message;
  final String description;
  final DateTime? dueAt;

  factory Reminder.fromJson(Map<String, dynamic> json) => Reminder(
        (json['id'] as num).toInt(),
        json['message'] as String? ?? '',
        json['description'] as String? ?? '',
        parseServerTime(json['due_at']),
      );
}

class AtlasNotification {
  AtlasNotification(this.id, this.message, this.read, this.createdAt);

  final int id;
  final String message;
  final bool read;
  final DateTime? createdAt;

  factory AtlasNotification.fromJson(Map<String, dynamic> json) => AtlasNotification(
        (json['id'] as num).toInt(),
        json['message'] as String? ?? '',
        json['read'] == true,
        parseServerTime(json['created_at']),
      );
}

class Device {
  Device(this.id, this.name, this.room, this.type, this.state);

  final String id;
  final String name;
  final String? room;
  final String type;
  final String state;

  bool get isOn => const {'on', 'encendido', 'unlocked', 'open', 'playing', 'heat', 'cool'}.contains(state.toLowerCase());

  factory Device.fromJson(Map<String, dynamic> json) => Device(
        json['id'] as String? ?? '',
        json['name'] as String? ?? '',
        json['room'] as String?,
        json['type'] as String? ?? '',
        json['state'] as String? ?? '',
      );
}

class Memory {
  Memory(this.id, this.content, this.category);

  final int id;
  final String content;
  final String category;

  factory Memory.fromJson(Map<String, dynamic> json) =>
      Memory((json['id'] as num).toInt(), json['content'] as String? ?? '', json['category'] as String? ?? '');
}

class Weather {
  Weather(this.place, this.temperature, this.feelsLike, this.description, this.icon, this.humidity, this.wind, this.days);

  final String place;
  final double temperature;
  final double feelsLike;
  final String description;
  final String icon;
  final int humidity;
  final double wind;
  final List<DayForecast> days;

  factory Weather.fromJson(Map<String, dynamic> json) => Weather(
        json['place'] as String? ?? '',
        (json['temperature_c'] as num?)?.toDouble() ?? 0,
        (json['feels_like_c'] as num?)?.toDouble() ?? 0,
        json['description'] as String? ?? '',
        json['icon'] as String? ?? '',
        (json['humidity'] as num?)?.toInt() ?? 0,
        (json['wind_kmh'] as num?)?.toDouble() ?? 0,
        [for (final d in (json['days'] as List? ?? [])) DayForecast.fromJson(d as Map<String, dynamic>)],
      );
}

class DayForecast {
  DayForecast(this.dayName, this.icon, this.min, this.max, this.rainChance);

  final String dayName;
  final String icon;
  final double min;
  final double max;
  final int? rainChance;

  factory DayForecast.fromJson(Map<String, dynamic> json) => DayForecast(
        json['day_name'] as String? ?? '',
        json['icon'] as String? ?? '',
        (json['min_c'] as num?)?.toDouble() ?? 0,
        (json['max_c'] as num?)?.toDouble() ?? 0,
        (json['rain_chance'] as num?)?.toInt(),
      );
}

class Headline {
  Headline(this.title, this.source, this.url);

  final String title;
  final String source;
  final String url;

  factory Headline.fromJson(Map<String, dynamic> json) =>
      Headline(json['title'] as String? ?? '', json['source'] as String? ?? '', json['url'] as String? ?? '');
}

