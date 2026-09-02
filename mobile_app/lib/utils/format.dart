/// Fecha corta en horario local, para las tarjetas de avisos y memoria.
/// El backend serializa datetimes sin zona (son de la misma máquina que
/// corre todo), así que se muestran tal cual vinieron.
String formatShortDate(DateTime date) {
  final now = DateTime.now();
  final time = '${date.hour.toString().padLeft(2, "0")}:${date.minute.toString().padLeft(2, "0")}';
  if (date.year == now.year && date.month == now.month && date.day == now.day) {
    return 'hoy $time';
  }
  return '${date.day.toString().padLeft(2, "0")}/${date.month.toString().padLeft(2, "0")} $time';
}
