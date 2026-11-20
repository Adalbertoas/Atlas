import 'package:flutter/material.dart';

import '../core/hands_free.dart';
import '../core/session.dart';
import '../ui/hud_art.dart';
import '../ui/markdown.dart';
import '../ui/theme.dart';
import 'voice_controls.dart';

/// Vista del núcleo a pantalla completa ("Ver núcleo" del escritorio): la
/// tablet como estación de voz. Tocar el núcleo es hablarle a ATLAS.
class CoreView extends StatelessWidget {
  const CoreView({super.key, required this.session});

  final Session session;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Hud.background,
      body: LayoutBuilder(
        builder: (context, outer) {
          // La retícula del fondo se centra donde está el núcleo (a la izquierda en horizontal).
          final wide = outer.maxWidth > 700;
          return Stack(
            children: [
              Positioned.fill(child: HudBackdrop(center: Alignment(wide ? -0.4 : 0, -0.04))),
              SafeArea(
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    final coreSize = (constraints.biggest.shortestSide * .62).clamp(180.0, 520.0);
                    return ListenableBuilder(
                      listenable: Listenable.merge([session.core, session.chat]),
                      builder: (context, _) {
                        final engine = session.engine;
                        final reply = session.chat.lastReply;
                        final heard = engine.heard;
                        return Column(
                          children: [
                            Padding(
                              padding: const EdgeInsets.fromLTRB(20, 14, 12, 0),
                              child: Row(
                                children: [
                                  Text('NEURAL CORE', style: Hud.title(size: 15, color: Hud.cyan)),
                                  const SizedBox(width: 12),
                                  Text(session.statusLabel.toUpperCase(), style: Hud.label(size: 11, color: Hud.text)),
                                  const Spacer(),
                                  IconButton(
                                    tooltip: 'Volver',
                                    onPressed: () => Navigator.of(context).pop(),
                                    icon: const Icon(Icons.close, color: Hud.muted),
                                  ),
                                ],
                              ),
                            ),
                            Expanded(
                              child: Row(
                                children: [
                                  Expanded(
                                    flex: 3,
                                    child: Center(
                                      child: GestureDetector(
                                        onTap: () => listenOnce(context, session),
                                        child: NeuralCore(session: session, size: coreSize),
                                      ),
                                    ),
                                  ),
                                  if (constraints.maxWidth > 700)
                                    Expanded(
                                      flex: 2,
                                      child: Padding(
                                        padding: const EdgeInsets.only(right: 28),
                                        child: _Transcript(heard: heard, reply: reply?.isError == false ? reply!.text : null),
                                      ),
                                    ),
                                ],
                              ),
                            ),
                            if (constraints.maxWidth <= 700) _Transcript(heard: heard, reply: reply?.isError == false ? reply!.text : null),
                            Padding(
                              padding: const EdgeInsets.fromLTRB(16, 4, 16, 18),
                              child: Wrap(
                                spacing: 10,
                                runSpacing: 10,
                                alignment: WrapAlignment.center,
                                children: [
                                  HudChip(
                                    label: engine.phase == ListenPhase.command ? 'ENVIAR AHORA' : 'HABLAR',
                                    icon: engine.phase == ListenPhase.command ? Icons.stop : Icons.mic_none,
                                    selected: engine.phase == ListenPhase.command,
                                    color: Hud.red,
                                    onTap: () => listenOnce(context, session),
                                  ),
                                  HudChip(
                                    label: 'ESCUCHAR "ATLAS"',
                                    icon: engine.handsFree ? Icons.hearing : Icons.hearing_disabled,
                                    selected: engine.handsFree,
                                    onTap: () => toggleHandsFree(context, session),
                                  ),
                                  HudChip(
                                    label: session.chat.speakReplies ? 'VOZ: SÍ' : 'VOZ: NO',
                                    icon: session.chat.speakReplies ? Icons.volume_up : Icons.volume_off,
                                    selected: session.chat.speakReplies,
                                    onTap: () => session.chat.speakReplies = !session.chat.speakReplies,
                                  ),
                                  if (session.voice.isSpeaking.value)
                                    HudChip(label: 'CALLAR', icon: Icons.stop_circle_outlined, onTap: session.voice.stopSpeaking),
                                ],
                              ),
                            ),
                          ],
                        );
                      },
                    );
                  },
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _Transcript extends StatelessWidget {
  const _Transcript({required this.heard, required this.reply});

  final String heard;
  final String? reply;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (heard.isNotEmpty) ...[
          Text('TÚ', style: Hud.label(size: 10, color: Hud.amber, spacing: .14)),
          const SizedBox(height: 4),
          Text('“$heard”', style: const TextStyle(fontSize: 17, height: 1.35, color: Hud.text)),
          const SizedBox(height: 18),
        ],
        if (reply != null && reply!.isNotEmpty) ...[
          Text('ATLAS', style: Hud.label(size: 10, color: Hud.cyan, spacing: .14)),
          const SizedBox(height: 4),
          ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 260),
            child: SingleChildScrollView(
              child: MarkdownText(reply!, style: const TextStyle(fontSize: 15, height: 1.5, color: Hud.text)),
            ),
          ),
        ],
        if (heard.isEmpty && (reply == null || reply!.isEmpty))
          Text('Toca el núcleo o di "Atlas" para hablarme.', style: Hud.label(size: 12, color: Hud.muted)),
      ],
    );
  }
}
