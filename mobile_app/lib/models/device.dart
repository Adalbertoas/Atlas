/// Espejo de DeviceOut (backend/app/smart_home/schemas.py).
class Device {
  final String id;
  final String name;
  final String? room;
  final String type;
  final String state;
  final Map<String, dynamic> capabilities;

  Device({
    required this.id,
    required this.name,
    required this.room,
    required this.type,
    required this.state,
    required this.capabilities,
  });

  factory Device.fromJson(Map<String, dynamic> json) {
    return Device(
      id: json['id'] as String,
      name: json['name'] as String,
      room: json['room'] as String?,
      type: json['type'] as String,
      state: json['state'] as String,
      capabilities: (json['capabilities'] as Map?)?.cast<String, dynamic>() ?? const {},
    );
  }

  // Mismo SAFE_TYPES que dashboard/app.js (y DeviceType en
  // app/smart_home/base.py, que llega en mayúsculas): solo estos tipos se
  // manejan con un interruptor simple on/off — el resto (cerraduras,
  // climatización, sensores) tiene estados que un switch no representa
  // bien, y algunos (cerraduras) son CRITICAL y siempre piden confirmación.
  static const _toggleableTypes = {'LIGHT', 'SWITCH', 'PLUG', 'FAN', 'TV'};

  bool get canToggle => _toggleableTypes.contains(type);

  bool get isOn => state == 'on';
}
