import 'models.dart';

/// Voces de ATLAS que ofrece el backend (Kokoro) y la elegida.
class VoiceCatalog {
  VoiceCatalog({
    required this.available,
    required this.current,
    required this.speed,
    required this.minSpeed,
    required this.maxSpeed,
    required this.voices,
  });

  final bool available;
  final String? current;
  final double speed;
  final double minSpeed;
  final double maxSpeed;
  final List<VoiceOption> voices;

  factory VoiceCatalog.fromJson(Map<String, dynamic> json) => VoiceCatalog(
        available: json['available'] == true,
        current: json['current'] as String?,
        speed: (json['speed'] as num?)?.toDouble() ?? 1,
        minSpeed: (json['min_speed'] as num?)?.toDouble() ?? 0.7,
        maxSpeed: (json['max_speed'] as num?)?.toDouble() ?? 1.4,
        voices: [for (final v in (json['voices'] as List? ?? [])) VoiceOption.fromJson(v as Map<String, dynamic>)],
      );
}

class VoiceOption {
  VoiceOption(this.id, this.name, this.gender, this.description);

  final String id;
  final String name;
  final String gender;
  final String description;

  factory VoiceOption.fromJson(Map<String, dynamic> json) => VoiceOption(
        json['id'] as String? ?? '',
        json['name'] as String? ?? '',
        json['gender'] as String? ?? '',
        json['description'] as String? ?? '',
      );
}

/// CPU y RAM de la PC donde corre ATLAS (medidores de la barra superior).
class PcStatus {
  PcStatus(this.cpu, this.ram, {this.pcOnline = true});

  /// null = la PC está apagada (ATLAS en el servidor, sin agente conectado).
  final double? cpu;
  final double? ram;
  final bool pcOnline;

  factory PcStatus.fromJson(Map<String, dynamic> json) => PcStatus(
        (json['cpu_percent'] as num?)?.toDouble(),
        (json['ram_percent'] as num?)?.toDouble(),
        pcOnline: json['pc_online'] != false,
      );
}

class ActivityEntry {
  ActivityEntry(this.tool, this.success, this.summary, this.createdAt);

  final String tool;
  final bool success;
  final String summary;
  final DateTime? createdAt;

  factory ActivityEntry.fromJson(Map<String, dynamic> json) => ActivityEntry(
        json['tool_name'] as String? ?? '',
        json['success'] != false,
        json['result_summary'] as String? ?? '',
        parseServerTime(json['created_at']),
      );

  /// Lo mismo que muestra el escritorio en "Actividad reciente" (TOOL_LABELS).
  String get label => toolLabels[tool] ?? tool.replaceAll('_', ' ');
}

const toolLabels = {
  'get_weather': 'Consultó el clima',
  'get_news': 'Buscó noticias',
  'convert_currency': 'Convirtió divisas',
  'calculate': 'Hizo un cálculo',
  'generate_password': 'Generó una contraseña',
  'open_website': 'Abrió una web',
  'set_volume': 'Ajustó el volumen',
  'lock_computer': 'Bloqueó la PC',
  'web_search': 'Buscó en internet',
  'read_web_page': 'Leyó una página',
  'get_system_info': 'Revisó el sistema',
  'get_current_time': 'Consultó la hora',
  'open_application': 'Abrió una aplicación',
  'close_application': 'Cerró una aplicación',
  'list_processes': 'Listó procesos',
  'open_file': 'Abrió un archivo',
  'control_media': 'Controló la música',
  'list_files': 'Listó archivos',
  'search_files': 'Buscó archivos',
  'search_documents': 'Buscó en documentos',
  'create_memory': 'Guardó un recuerdo',
  'search_memory': 'Consultó su memoria',
  'create_reminder': 'Creó un recordatorio',
  'list_reminders': 'Revisó recordatorios',
  'cancel_reminder': 'Canceló un recordatorio',
  'read_clipboard': 'Leyó el portapapeles',
  'write_clipboard': 'Copió al portapapeles',
  'manage_window': 'Movió una ventana',
  'save_screenshot': 'Guardó una captura',
  'analyze_screenshot': 'Miró la pantalla',
  'daily_briefing': 'Preparó el resumen del día',
  'list_devices': 'Revisó dispositivos',
  'set_device_state': 'Controló un dispositivo',
  'control_room': 'Controló una habitación',
  'run_routine': 'Ejecutó una rutina',
  'query_world': 'Consultó el mundo',
  'show_world_view': 'Mostró el mapa',
  'create_spreadsheet': 'Creó un Excel',
  'generate_image': 'Creó una imagen',
  'draw_vector': 'Dibujó un vector',
};
