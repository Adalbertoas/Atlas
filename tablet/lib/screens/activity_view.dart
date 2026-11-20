import 'package:flutter/material.dart';

import '../core/models_extra.dart';
import '../core/session.dart';
import '../ui/theme.dart';

/// "Actividad reciente": las herramientas que usó ATLAS (en la PC o la tablet).
class ActivityView extends StatefulWidget {
  const ActivityView({super.key, required this.session});

  final Session session;

  @override
  State<ActivityView> createState() => _ActivityViewState();
}

class _ActivityViewState extends State<ActivityView> {
  late Future<List<ActivityEntry>> _items = widget.session.api.activity();

  void _reload() => setState(() => _items = widget.session.api.activity());

  static String _ago(DateTime? time) {
    if (time == null) return '';
    final minutes = DateTime.now().difference(time).inMinutes;
    if (minutes < 1) return 'recién';
    if (minutes < 60) return 'hace $minutes minutos';
    if (minutes < 60 * 24) return 'hace ${minutes ~/ 60} h';
    return 'hace ${minutes ~/ (60 * 24)} días';
  }

  @override
  Widget build(BuildContext context) {
    return HudPanel(
      title: 'Actividad reciente',
      icon: Icons.blur_on,
      trailing: IconButton(tooltip: 'Actualizar', onPressed: _reload, icon: const Icon(Icons.refresh, size: 18, color: Hud.cyan)),
      child: FutureBuilder<List<ActivityEntry>>(
        future: _items,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
          if (snapshot.hasError) return Center(child: Text('${snapshot.error}', style: const TextStyle(color: Hud.red)));
          final items = snapshot.data ?? [];
          if (items.isEmpty) return Center(child: Text('Sin actividad todavía.', style: Hud.label(size: 12)));
          return RefreshIndicator(
            onRefresh: () async => _reload(),
            child: ListView.separated(
              itemCount: items.length,
              separatorBuilder: (_, _) => const Divider(height: 1, color: Hud.line),
              itemBuilder: (context, i) {
                final a = items[i];
                final color = a.success ? Hud.green : Hud.red;
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Container(
                      width: 8,
                      height: 8,
                      margin: const EdgeInsets.only(top: 5, right: 12),
                      decoration: BoxDecoration(color: color, shape: BoxShape.circle, boxShadow: [BoxShadow(color: color, blurRadius: 6)]),
                    ),
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(a.label, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
                        const SizedBox(height: 2),
                        Text(a.summary, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(color: Hud.muted, fontSize: 12.5)),
                      ]),
                    ),
                    const SizedBox(width: 10),
                    Text(_ago(a.createdAt), style: Hud.label(size: 9.5)),
                  ]),
                );
              },
            ),
          );
        },
      ),
    );
  }
}
