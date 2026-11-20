import 'package:flutter/material.dart';

import '../core/models.dart';
import '../core/session.dart';
import '../ui/theme.dart';

/// Dispositivos de la casa por habitación. Tocar uno se lo pide a ATLAS por el
/// chat, así pasa por el mismo control de permisos (una cerradura pide confirmación).
class DevicesView extends StatefulWidget {
  const DevicesView({super.key, required this.session, required this.onAsk});

  final Session session;
  final ValueChanged<String> onAsk;

  @override
  State<DevicesView> createState() => _DevicesViewState();
}

class _DevicesViewState extends State<DevicesView> {
  late Future<List<Device>> _devices = widget.session.api.devices();

  void _reload() => setState(() => _devices = widget.session.api.devices());

  static IconData _icon(String type) => switch (type.toLowerCase()) {
        'light' => Icons.lightbulb_outline,
        'switch' || 'plug' => Icons.power_outlined,
        'lock' => Icons.lock_outline,
        'climate' || 'thermostat' => Icons.thermostat,
        'media_player' || 'tv' => Icons.tv,
        'fan' => Icons.mode_fan_off_outlined,
        'cover' || 'blind' => Icons.blinds_outlined,
        'sensor' => Icons.sensors,
        'camera' => Icons.videocam_outlined,
        _ => Icons.devices_other,
      };

  /// Lo que se le pide a ATLAS al tocar el dispositivo.
  static String _request(Device d) => switch (d.type.toLowerCase()) {
        'light' || 'switch' || 'plug' || 'fan' || 'tv' => '${d.isOn ? 'Apaga' : 'Enciende'} ${d.name}',
        'lock' => '${d.state.toLowerCase() == 'locked' ? 'Abre' : 'Cierra'} ${d.name}',
        _ => '¿Cómo está ${d.name}?',
      };

  @override
  Widget build(BuildContext context) {
    return HudPanel(
      title: 'Casa',
      icon: Icons.home_outlined,
      trailing: IconButton(tooltip: 'Actualizar', onPressed: _reload, icon: const Icon(Icons.refresh, color: Hud.cyan)),
      child: FutureBuilder<List<Device>>(
        future: _devices,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) return const Center(child: CircularProgressIndicator());
          if (snapshot.hasError) return Center(child: Text('${snapshot.error}', style: const TextStyle(color: Hud.red)));
          final devices = snapshot.data ?? [];
          if (devices.isEmpty) {
            return const Center(child: Text('No hay dispositivos. Conecta Home Assistant en el backend.', style: TextStyle(color: Hud.muted)));
          }
          final rooms = <String, List<Device>>{};
          for (final d in devices) {
            rooms.putIfAbsent(d.room ?? 'Sin habitación', () => []).add(d);
          }
          return ListView(children: [
            for (final entry in rooms.entries) ...[
              Padding(
                padding: const EdgeInsets.fromLTRB(4, 8, 4, 8),
                child: Text(entry.key.toUpperCase(), style: const TextStyle(color: Hud.muted, letterSpacing: 2, fontSize: 12, fontWeight: FontWeight.w700)),
              ),
              Wrap(spacing: 10, runSpacing: 10, children: [
                for (final d in entry.value)
                  SizedBox(
                    width: 170,
                    child: InkWell(
                      borderRadius: BorderRadius.circular(6),
                      onTap: () => widget.onAsk(_request(d)),
                      child: Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: d.isOn ? const Color(0x263FE6FF) : Hud.fill,
                          border: Border.all(color: d.isOn ? Hud.cyan : Hud.line2),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Icon(_icon(d.type), color: d.isOn ? Hud.cyan : Hud.muted),
                          const SizedBox(height: 8),
                          Text(d.name, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w600)),
                          Text(d.state, style: TextStyle(color: d.isOn ? Hud.cyan : Hud.muted, fontSize: 12)),
                        ]),
                      ),
                    ),
                  ),
              ]),
            ],
          ]);
        },
      ),
    );
  }
}
