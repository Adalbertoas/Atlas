import 'dart:async';

import 'package:flutter/material.dart';

import '../core/models.dart';
import '../core/session.dart';
import '../ui/theme.dart';

/// Panel «Hoy»: hora, clima, recordatorios, avisos y titulares.
/// `compact` = columna lateral junto al chat (tablet en horizontal).
class TodayView extends StatefulWidget {
  const TodayView({super.key, required this.session, required this.onAsk, this.compact = false});

  final Session session;
  final ValueChanged<String> onAsk;
  final bool compact;

  @override
  State<TodayView> createState() => _TodayViewState();
}

class _TodayViewState extends State<TodayView> {
  Weather? _weather;
  String? _weatherError;
  List<Reminder> _reminders = [];
  List<AtlasNotification> _notifications = [];
  List<Headline> _news = [];
  bool _loading = true;
  Timer? _clock;
  Timer? _refresh;

  @override
  void initState() {
    super.initState();
    _load();
    _clock = Timer.periodic(const Duration(seconds: 20), (_) => setState(() {}));
    _refresh = Timer.periodic(const Duration(minutes: 5), (_) => _load());
  }

  @override
  void dispose() {
    _clock?.cancel();
    _refresh?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    final api = widget.session.api;
    // Cada bloque se carga por su cuenta: que falle el clima (ej. sin ciudad
    // configurada) no deja colgados los recordatorios ni los titulares.
    Future<void> guarded(Future<void> Function() load) async {
      try {
        await load();
      } catch (_) {}
    }

    await Future.wait([
      () async {
        try {
          _weather = await api.weather();
          _weatherError = null;
        } catch (error) {
          _weather = null;
          _weatherError = '$error';
        }
      }(),
      guarded(() async => _reminders = await api.reminders()),
      guarded(() async => _notifications = await api.notifications()),
      guarded(() async => _news = await api.news()),
    ]);
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _cancelReminder(Reminder reminder) async {
    try {
      await widget.session.api.cancelReminder(reminder.id);
      setState(() => _reminders.remove(reminder));
    } catch (error) {
      if (mounted) showMessage(context, '$error');
    }
  }

  Future<void> _markRead(AtlasNotification notification) async {
    try {
      await widget.session.api.markNotificationRead(notification.id);
      await _load();
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final unread = _notifications.where((n) => !n.read).toList();
    final children = <Widget>[
      // En la columna junto al chat la hora ya está en la barra superior.
      if (!widget.compact) _clockCard(),
      _weatherCard(),
      HudPanel(
        title: 'Recordatorios',
        icon: Icons.notifications_active_outlined,
        trailing: IconButton(
          tooltip: 'Nuevo recordatorio',
          icon: const Icon(Icons.add, size: 20, color: Hud.cyan),
          onPressed: () => widget.onAsk('Quiero crear un recordatorio'),
        ),
        child: _reminders.isEmpty
            ? const _Empty('Sin recordatorios pendientes.')
            : Column(children: [
                for (final r in _reminders.take(widget.compact ? 4 : 20))
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    dense: true,
                    leading: const Icon(Icons.schedule, color: Hud.cyan, size: 20),
                    title: Text(r.message),
                    subtitle: Text(r.description, style: const TextStyle(color: Hud.muted)),
                    trailing: IconButton(
                      tooltip: 'Cancelar',
                      icon: const Icon(Icons.close, size: 18, color: Hud.muted),
                      onPressed: () => _cancelReminder(r),
                    ),
                  ),
              ]),
      ),
      if (unread.isNotEmpty || !widget.compact)
        HudPanel(
          title: 'Avisos${unread.isEmpty ? '' : ' (${unread.length})'}',
          icon: Icons.campaign_outlined,
          child: unread.isEmpty
              ? const _Empty('Nada nuevo.')
              : Column(children: [
                  for (final n in unread.take(widget.compact ? 3 : 10))
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      dense: true,
                      leading: const Icon(Icons.circle, size: 10, color: Hud.amber),
                      title: Text(n.message, maxLines: 3, overflow: TextOverflow.ellipsis),
                      subtitle: n.createdAt == null ? null : Text(_ago(n.createdAt!), style: const TextStyle(color: Hud.muted)),
                      onTap: () => _markRead(n),
                    ),
                ]),
        ),
      HudPanel(
        title: 'Titulares',
        icon: Icons.newspaper,
        trailing: TextButton(onPressed: () => widget.onAsk('Dame un resumen de las noticias de hoy'), child: const Text('Resumir')),
        child: _news.isEmpty
            ? const _Empty('Sin titulares por ahora.')
            : Column(children: [
                for (final h in _news.take(widget.compact ? 3 : 8))
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    dense: true,
                    title: Text(h.title, maxLines: 2, overflow: TextOverflow.ellipsis),
                    subtitle: Text(h.source, style: const TextStyle(color: Hud.muted)),
                    onTap: () => widget.onAsk('Cuéntame más sobre esta noticia: "${h.title}" (${h.source})'),
                  ),
              ]),
      ),
    ];

    return RefreshIndicator(
      onRefresh: _load,
      child: _loading
          ? const Center(child: CircularProgressIndicator())
          : widget.compact
              ? ListView.separated(
                  itemCount: children.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 12),
                  itemBuilder: (_, i) => children[i],
                )
              : LayoutBuilder(builder: (context, constraints) {
                  // A pantalla completa en horizontal: dos columnas.
                  if (constraints.maxWidth < 700) {
                    return ListView.separated(
                      itemCount: children.length,
                      separatorBuilder: (_, _) => const SizedBox(height: 12),
                      itemBuilder: (_, i) => children[i],
                    );
                  }
                  final left = [children[0], children[1], children[2]];
                  final right = children.sublist(3);
                  Widget column(List<Widget> items) =>
                      Column(children: [for (final w in items) Padding(padding: const EdgeInsets.only(bottom: 12), child: w)]);
                  return ListView(children: [
                    Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Expanded(child: column(left)),
                      const SizedBox(width: 12),
                      Expanded(child: column(right)),
                    ]),
                  ]);
                }),
    );
  }

  Widget _clockCard() {
    final now = DateTime.now();
    const days = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];
    const months = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
    final time = '${now.hour.toString().padLeft(2, '0')}:${now.minute.toString().padLeft(2, '0')}';
    return HudPanel(
      child: Row(children: [
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(days[now.weekday - 1].toUpperCase(), style: const TextStyle(color: Hud.muted, letterSpacing: 2, fontSize: 12)),
            Text('${now.day} de ${months[now.month - 1]}', style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
          ]),
        ),
        Text(time, style: const TextStyle(fontSize: 38, fontWeight: FontWeight.w300, color: Hud.cyan, letterSpacing: 2)),
      ]),
    );
  }

  Widget _weatherCard() {
    final w = _weather;
    return HudPanel(
      title: 'Clima',
      icon: Icons.thermostat,
      child: w == null
          ? _Empty(_weatherError ?? 'Sin datos del clima.')
          : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Icon(weatherIcon(w.icon), size: 42, color: Hud.amber),
                const SizedBox(width: 12),
                Text('${w.temperature.round()}°', style: const TextStyle(fontSize: 36, fontWeight: FontWeight.w300)),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(w.description, style: const TextStyle(fontWeight: FontWeight.w600)),
                    Text(w.place, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(color: Hud.muted, fontSize: 12)),
                    Text('Sensación ${w.feelsLike.round()}° · humedad ${w.humidity}%', style: const TextStyle(color: Hud.muted, fontSize: 12)),
                  ]),
                ),
              ]),
              if (w.days.isNotEmpty) ...[
                const SizedBox(height: 10),
                Row(children: [
                  for (final d in w.days.take(4))
                    Expanded(
                      child: Column(children: [
                        Text(d.dayName.length > 3 ? d.dayName.substring(0, 3) : d.dayName,
                            style: const TextStyle(color: Hud.muted, fontSize: 12)),
                        Icon(weatherIcon(d.icon), size: 20, color: Hud.amber),
                        Text('${d.min.round()}° / ${d.max.round()}°', style: const TextStyle(fontSize: 12)),
                      ]),
                    ),
                ]),
              ],
            ]),
    );
  }

  static String _ago(DateTime time) {
    final minutes = DateTime.now().difference(time).inMinutes;
    if (minutes < 1) return 'recién';
    if (minutes < 60) return 'hace $minutes min';
    if (minutes < 60 * 24) return 'hace ${minutes ~/ 60} h';
    return 'hace ${minutes ~/ (60 * 24)} días';
  }
}

IconData weatherIcon(String icon) => switch (icon) {
      'sun' => Icons.wb_sunny_outlined,
      'partly' => Icons.wb_cloudy_outlined,
      'cloud' => Icons.cloud_outlined,
      'fog' => Icons.foggy,
      'drizzle' || 'rain' => Icons.water_drop_outlined,
      'snow' => Icons.ac_unit,
      'storm' => Icons.thunderstorm_outlined,
      _ => Icons.wb_cloudy_outlined,
    };

class _Empty extends StatelessWidget {
  const _Empty(this.text);

  final String text;

  @override
  Widget build(BuildContext context) =>
      Padding(padding: const EdgeInsets.symmetric(vertical: 6), child: Text(text, style: const TextStyle(color: Hud.muted)));
}
