import 'package:flutter/material.dart';

import '../core/session.dart';
import '../ui/theme.dart';

/// Mismo aviso que el escritorio (HANDS_FREE_PRIVACY), adaptado a la tablet.
const handsFreePrivacy =
    'ATLAS mantendrá el micrófono abierto esperando la palabra "Atlas". El sonido se analiza en la tablet; '
    'solo las frases con voz se envían al backend de ATLAS en tu PC para transcribirlas, y no se guardan. '
    'Mientras escucha, la pantalla queda encendida.';

/// Enciende o apaga "Escuchar «Atlas»"; la primera vez pide consentimiento.
Future<void> toggleHandsFree(BuildContext context, Session session) async {
  final engine = session.engine;
  if (!engine.handsFree && !session.prefs.handsFreeConsent) {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('ESCUCHAR "ATLAS"', style: Hud.title(size: 18)),
        content: const Text(handsFreePrivacy, style: TextStyle(height: 1.5)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('CANCELAR')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('ACTIVAR')),
        ],
      ),
    );
    if (ok != true) return;
    session.prefs.handsFreeConsent = true;
  }
  final notice = await engine.setHandsFree(!engine.handsFree);
  if (!context.mounted) return;
  showMessage(context, notice ?? (engine.handsFree ? 'Te escucho: di "Atlas" y tu pedido.' : 'Manos libres apagado.'));
}

/// Botón del micrófono: escuchar un pedido (o enviarlo si ya estaba escuchando).
Future<void> listenOnce(BuildContext context, Session session) async {
  final notice = await session.engine.listenOnce();
  if (notice != null && context.mounted) showMessage(context, notice);
}
