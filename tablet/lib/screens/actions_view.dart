import 'package:flutter/material.dart';

import '../core/session.dart';
import '../ui/theme.dart';

/// Acciones rápidas: las mismas que el panel del escritorio (DataPanels.tsx),
/// más "Factura a Excel". Solo se muestran las que el backend puede hacer.
class ActionsView extends StatefulWidget {
  const ActionsView({super.key, required this.session, required this.onAsk, this.compact = false});

  final Session session;
  final ValueChanged<String> onAsk;
  final bool compact;

  @override
  State<ActionsView> createState() => _ActionsViewState();
}

class _ActionsViewState extends State<ActionsView> {
  static const _actions = [
    (Icons.today_outlined, 'Resumen del día', 'Dame mi resumen del día', 'daily_briefing'),
    (Icons.wb_cloudy_outlined, 'Clima', '¿Cómo está el clima hoy y los próximos días?', 'get_weather'),
    (Icons.article_outlined, 'Noticias', '¿Cuáles son las noticias más importantes de hoy?', 'get_news'),
    (Icons.attach_money, 'Divisas', '¿A cuánto está el dólar hoy?', 'convert_currency'),
    (Icons.calculate_outlined, 'Calcular', 'Calcula ', 'calculate'),
    (Icons.key_outlined, 'Contraseña', 'Genérame una contraseña segura', 'generate_password'),
    (Icons.alarm_add_outlined, 'Recordatorio', 'Recuérdame ', 'create_reminder'),
    (Icons.receipt_long_outlined, 'Factura a Excel', '', 'create_spreadsheet'),
    (Icons.monitor_outlined, 'Mira mi pantalla', 'Mira mi pantalla y dime qué ves', 'analyze_screenshot'),
    (Icons.music_note_outlined, 'Música', 'Pausa la música', 'control_media'),
    (Icons.volume_up_outlined, 'Volumen 50 %', 'Pon el volumen al 50 %', 'set_volume'),
    (Icons.image_outlined, 'Crear imagen', 'Crea una imagen de ', 'generate_image'),
    (Icons.draw_outlined, 'Dibujar logo', 'Dibuja un logo para ', 'draw_vector'),
    (Icons.public, 'Buscar en web', 'Busca en internet ', 'web_search'),
    (Icons.lock_outline, 'Bloquear PC', 'Bloquea la computadora', 'lock_computer'),
  ];

  Set<String>? _tools;

  @override
  void initState() {
    super.initState();
    widget.session.api.toolNames().then((t) {
      if (mounted) setState(() => _tools = t);
    }, onError: (_) {});
  }

  void _run(String label, String prompt) {
    if (label == 'Factura a Excel') {
      // Abre el chat con la cámara lista y el pedido escrito.
      final chat = widget.session.chat;
      chat.draft.value = 'Pásalo a Excel';
      chat.cameraRequested.value = true;
      widget.onAsk('');
      return;
    }
    widget.onAsk(prompt);
  }

  @override
  Widget build(BuildContext context) {
    final tools = _tools;
    final actions = [for (final a in _actions) if (tools == null || tools.contains(a.$4)) a];
    final shown = widget.compact ? actions.take(9).toList() : actions;
    final grid = GridView.builder(
      shrinkWrap: widget.compact,
      physics: widget.compact ? const NeverScrollableScrollPhysics() : null,
      gridDelegate: SliverGridDelegateWithMaxCrossAxisExtent(
        maxCrossAxisExtent: widget.compact ? 84 : 140,
        mainAxisExtent: widget.compact ? 66 : 96,
        crossAxisSpacing: 6,
        mainAxisSpacing: 6,
      ),
      itemCount: shown.length,
      itemBuilder: (context, i) {
        final (icon, label, prompt, _) = shown[i];
        return _ActionTile(icon: icon, label: label, compact: widget.compact, onTap: () => _run(label, prompt));
      },
    );
    return HudPanel(
      title: 'Acciones rápidas',
      icon: Icons.handyman_outlined,
      padding: EdgeInsets.all(widget.compact ? 8 : 14),
      child: grid,
    );
  }
}

class _ActionTile extends StatelessWidget {
  const _ActionTile({required this.icon, required this.label, required this.compact, required this.onTap});

  final IconData icon;
  final String label;
  final bool compact;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: const Color(0x99031220),
      shape: RoundedRectangleBorder(side: const BorderSide(color: Hud.line), borderRadius: BorderRadius.circular(3)),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(3),
        splashColor: Hud.fill2,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            Icon(icon, size: compact ? 20 : 28, color: Hud.cyan, shadows: const [Shadow(color: Color(0x663FE6FF), blurRadius: 6)]),
            SizedBox(height: compact ? 4 : 8),
            Text(label,
                textAlign: TextAlign.center,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: compact ? 10.5 : 13, height: 1.1, color: Hud.text)),
          ]),
        ),
      ),
    );
  }
}
