/// Espejo de NotificationOut (backend/app/notifications/schemas.py).
class NotificationItem {
  final int id;
  final String message;
  final bool read;
  final DateTime createdAt;

  NotificationItem({
    required this.id,
    required this.message,
    required this.read,
    required this.createdAt,
  });

  factory NotificationItem.fromJson(Map<String, dynamic> json) {
    return NotificationItem(
      id: json['id'] as int,
      message: json['message'] as String,
      read: json['read'] as bool? ?? false,
      // El backend serializa datetimes naive (hora local del servidor);
      // parsearlos como UTC correría todo por el huso del celular.
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ?? DateTime.now(),
    );
  }
}
