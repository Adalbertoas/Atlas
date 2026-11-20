import 'package:flutter/material.dart';

import '../core/api.dart';
import '../core/session.dart';
import '../ui/theme.dart';
import 'voice_controls.dart';

class SettingsView extends StatefulWidget {
  const SettingsView({super.key, required this.session, required this.onDisconnect});

  final Session session;
  final VoidCallback onDisconnect;

  @override
  State<SettingsView> createState() => _SettingsViewState();
}

class _SettingsViewState extends State<SettingsView> {
  late Future<Map<String, dynamic>> _health = widget.session.api.health();

  Future<void> _confirmDisconnect() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('¿DESCONECTAR LA TABLET?', style: Hud.title(size: 17)),
        content: const Text('Se borran la dirección, la huella del certificado y la contraseña guardadas en esta tablet.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('CANCELAR')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('DESCONECTAR')),
        ],
      ),
    );
    if (ok == true) widget.onDisconnect();
  }

  @override
  Widget build(BuildContext context) {
    final session = widget.session;
    final config = session.config;
    final sections = [
      _VoicePicker(session: session),
      _HandsFreeSettings(session: session),
      HudPanel(
        title: 'Conexión',
        icon: Icons.hub_outlined,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          _row('Servidor', config.baseUrl),
          _row(
            'Certificado',
            config.fingerprint != null
                ? AtlasApi.prettyFingerprint(config.fingerprint!)
                : (config.uri.scheme == 'https' ? 'público, verificado por Android' : 'sin cifrar (http)'),
            mono: config.fingerprint != null,
          ),
          _row('Contraseña', config.password.isEmpty ? 'no se usa' : 'guardada de forma segura'),
          FutureBuilder(
            future: _health,
            builder: (context, snapshot) {
              final done = snapshot.connectionState == ConnectionState.done;
              final ok = snapshot.hasData;
              return _row(
                'Estado',
                !done ? 'comprobando…' : (ok ? 'en línea · IA: ${snapshot.data!['ai_provider'] ?? '?'}' : '${snapshot.error}'),
                color: !done ? Hud.muted : (ok ? Hud.green : Hud.red),
              );
            },
          ),
          const SizedBox(height: 10),
          Wrap(spacing: 10, runSpacing: 10, children: [
            OutlinedButton.icon(
              onPressed: () => setState(() => _health = session.api.health()),
              icon: const Icon(Icons.refresh, size: 18),
              label: const Text('PROBAR CONEXIÓN'),
            ),
            OutlinedButton.icon(
              onPressed: _confirmDisconnect,
              icon: const Icon(Icons.link_off, color: Hud.red, size: 18),
              label: const Text('DESCONECTAR TABLET'),
            ),
          ]),
        ]),
      ),
    ];
    return LayoutBuilder(builder: (context, constraints) {
      if (constraints.maxWidth < 760) {
        return ListView.separated(
          itemCount: sections.length,
          separatorBuilder: (_, _) => const SizedBox(height: 12),
          itemBuilder: (_, i) => sections[i],
        );
      }
      return ListView(children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(child: sections[0]),
          const SizedBox(width: 12),
          Expanded(child: Column(children: [sections[1], const SizedBox(height: 12), sections[2]])),
        ]),
      ]);
    });
  }

  Widget _row(String label, String value, {bool mono = false, Color? color}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(width: 100, child: Text(label.toUpperCase(), style: Hud.label(size: 10))),
        Expanded(
          child: SelectableText(value, style: TextStyle(fontFamily: mono ? Hud.mono : null, fontSize: mono ? 11 : 13.5, color: color ?? Hud.text)),
        ),
      ]),
    );
  }
}

/// Elegir la voz de ATLAS (para la PC y la tablet) y su velocidad.
class _VoicePicker extends StatefulWidget {
  const _VoicePicker({required this.session});

  final Session session;

  @override
  State<_VoicePicker> createState() => _VoicePickerState();
}

class _VoicePickerState extends State<_VoicePicker> {
  VoiceCatalog? _catalog;
  String? _error;
  String? _selected;
  double _speed = 1;
  String? _previewing;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final catalog = await widget.session.api.voices();
      if (!mounted) return;
      setState(() {
        _catalog = catalog;
        _selected = catalog.current;
        _speed = catalog.speed.clamp(catalog.minSpeed, catalog.maxSpeed);
        _error = null;
      });
    } catch (error) {
      if (mounted) setState(() => _error = '$error');
    }
  }

  Future<void> _preview(VoiceOption voice) async {
    setState(() => _previewing = voice.id);
    final session = widget.session;
    try {
      final name = session.assistantName.value;
      final wav = await session.api.speak('Hola, soy $name. Así sonaría mi voz si eliges a ${voice.name}.', voice: voice.id, speed: _speed);
      session.engine.suspend();
      try {
        await session.voice.speak(wav);
      } finally {
        session.engine.resume();
      }
    } catch (error) {
      if (mounted) showMessage(context, '$error');
    } finally {
      if (mounted) setState(() => _previewing = null);
    }
  }

  Future<void> _save() async {
    final voice = _selected;
    if (voice == null) return;
    setState(() => _saving = true);
    try {
      final catalog = await widget.session.api.chooseVoice(voice, double.parse(_speed.toStringAsFixed(2)));
      if (!mounted) return;
      setState(() => _catalog = catalog);
      final name = catalog.voices.where((v) => v.id == voice).firstOrNull?.name ?? voice;
      showMessage(context, 'Listo: ATLAS ahora habla con la voz de $name (también en la PC).');
    } catch (error) {
      if (mounted) showMessage(context, '$error');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final catalog = _catalog;
    Widget body;
    if (_error != null) {
      body = Text(_error!, style: const TextStyle(color: Hud.red));
    } else if (catalog == null) {
      body = const Padding(padding: EdgeInsets.all(12), child: Center(child: CircularProgressIndicator()));
    } else if (!catalog.available) {
      body = const Text(
        'El backend usa una voz fija. Para elegir entre varias voces, configura TTS_PROVIDER=kokoro en backend/.env.',
        style: TextStyle(color: Hud.muted),
      );
    } else {
      final changed = _selected != catalog.current || (_speed - catalog.speed).abs() > .01;
      body = Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        for (final voice in catalog.voices) _voiceTile(voice, catalog.current == voice.id),
        const SizedBox(height: 10),
        Row(children: [
          Text('VELOCIDAD', style: Hud.label(size: 10)),
          Expanded(
            child: Slider(
              value: _speed,
              min: catalog.minSpeed,
              max: catalog.maxSpeed,
              divisions: ((catalog.maxSpeed - catalog.minSpeed) / .05).round(),
              label: '${_speed.toStringAsFixed(2)}x',
              onChanged: (v) => setState(() => _speed = v),
            ),
          ),
          SizedBox(width: 44, child: Text('${_speed.toStringAsFixed(2)}x', style: Hud.label(size: 11, color: Hud.text))),
        ]),
        const SizedBox(height: 6),
        FilledButton.icon(
          onPressed: changed && !_saving ? _save : null,
          icon: _saving ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.check, size: 18),
          label: Text(changed ? 'USAR ESTA VOZ' : 'VOZ EN USO'),
        ),
        const SizedBox(height: 6),
        Text('La voz se cambia en el backend: la PC y la tablet hablan igual.', style: Hud.label(size: 9.5, spacing: .02)),
      ]);
    }
    return HudPanel(title: 'Voz de ATLAS', icon: Icons.record_voice_over_outlined, child: body);
  }

  Widget _voiceTile(VoiceOption voice, bool current) {
    final selected = _selected == voice.id;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Material(
        color: selected ? const Color(0x1F3FE6FF) : const Color(0x80031220),
        shape: RoundedRectangleBorder(side: BorderSide(color: selected ? Hud.cyan : Hud.line), borderRadius: BorderRadius.circular(3)),
        child: InkWell(
          onTap: () => setState(() => _selected = voice.id),
          borderRadius: BorderRadius.circular(3),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(12, 10, 6, 10),
            child: Row(children: [
              Icon(voice.gender == 'mujer' ? Icons.face_3_outlined : Icons.face_6_outlined, color: selected ? Hud.cyan : Hud.muted),
              const SizedBox(width: 12),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    Text(voice.name.toUpperCase(), style: Hud.title(size: 15, color: selected ? Hud.bright : Hud.text)),
                    const SizedBox(width: 8),
                    Text(voice.gender.toUpperCase(), style: Hud.label(size: 9.5)),
                    if (current) ...[const SizedBox(width: 8), Text('· EN USO', style: Hud.label(size: 9.5, color: Hud.green))],
                  ]),
                  const SizedBox(height: 2),
                  Text(voice.description, style: const TextStyle(color: Hud.muted, fontSize: 12.5)),
                ]),
              ),
              IconButton(
                tooltip: 'Escuchar',
                onPressed: _previewing == null ? () => _preview(voice) : null,
                icon: _previewing == voice.id
                    ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.play_circle_outline, color: Hud.cyan),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}

/// "Escuchar «Atlas»" y respuestas habladas (ListeningSettings del escritorio).
class _HandsFreeSettings extends StatelessWidget {
  const _HandsFreeSettings({required this.session});

  final Session session;

  @override
  Widget build(BuildContext context) {
    final engine = session.engine;
    final prefs = session.prefs;
    return ListenableBuilder(
      listenable: Listenable.merge([engine, session.chat]),
      builder: (context, _) => HudPanel(
        title: 'Escucha por voz',
        icon: Icons.hearing,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          _switch(
            'Escuchar "Atlas"',
            'Di "Atlas" y tu pedido sin tocar la tablet. La pantalla queda encendida mientras escucha.',
            engine.handsFree,
            (_) => toggleHandsFree(context, session),
          ),
          _switch(
            'Responder siempre con voz',
            'Lee en voz alta todas las respuestas, también las de mensajes escritos.',
            session.chat.speakReplies,
            (v) => session.chat.speakReplies = v,
          ),
          _switch(
            'Seguir la conversación',
            'Después de responder, unos segundos para hablar otra vez sin decir "Atlas".',
            prefs.followUp,
            (v) {
              prefs.followUp = v;
              engine.refresh();
            },
          ),
          _switch(
            'Sonido al oír "Atlas"',
            'Un tono corto confirma que te escuchó.',
            prefs.wakeSound,
            (v) {
              prefs.wakeSound = v;
              engine.refresh();
            },
          ),
          const SizedBox(height: 8),
          Row(children: [
            Text('SENSIBILIDAD', style: Hud.label(size: 10)),
            Expanded(
              child: Slider(
                value: prefs.micSensitivity,
                divisions: 10,
                label: '${(prefs.micSensitivity * 100).round()} %',
                onChanged: (v) => engine.sensitivity = v,
              ),
            ),
          ]),
          Text('Baja: ignora voces lejanas y la tele. Alta: capta voz baja.', style: Hud.label(size: 9.5, spacing: .02)),
          const SizedBox(height: 10),
          if (engine.handsFree) _MicMeter(session: session) else Text('Activa la escucha para ver el nivel del micrófono.', style: Hud.label(size: 10, spacing: .02)),
        ]),
      ),
    );
  }

  Widget _switch(String title, String subtitle, bool value, ValueChanged<bool> onChanged) {
    return SwitchListTile(
      contentPadding: EdgeInsets.zero,
      dense: true,
      value: value,
      onChanged: onChanged,
      title: Text(title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
      subtitle: Text(subtitle, style: const TextStyle(color: Hud.muted, fontSize: 12)),
    );
  }
}

/// Nivel del micrófono frente al umbral de voz (para ajustar la sensibilidad).
class _MicMeter extends StatelessWidget {
  const _MicMeter({required this.session});

  final Session session;

  @override
  Widget build(BuildContext context) {
    final engine = session.engine;
    return ValueListenableBuilder(
      valueListenable: engine.level,
      builder: (context, _, _) {
        double pct(double db) => ((db + 80) / 80).clamp(0, 1).toDouble();
        final voice = engine.levelDb >= engine.thresholdDb;
        return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          LayoutBuilder(builder: (context, constraints) {
            final w = constraints.maxWidth;
            return SizedBox(
              height: 12,
              child: Stack(children: [
                Container(decoration: BoxDecoration(color: Hud.fill2, borderRadius: BorderRadius.circular(2))),
                AnimatedContainer(
                  duration: const Duration(milliseconds: 80),
                  width: w * pct(engine.levelDb),
                  decoration: BoxDecoration(color: voice ? Hud.green : Hud.cyan, borderRadius: BorderRadius.circular(2)),
                ),
                Positioned(left: w * pct(engine.thresholdDb) - 1, top: -2, bottom: -2, child: Container(width: 2, color: Hud.amber)),
              ]),
            );
          }),
          const SizedBox(height: 6),
          Text(
            '${voice ? 'Voz detectada' : 'Silencio'} · fondo ${engine.noiseFloorDb.round()} dB · umbral ${engine.thresholdDb.round()} dB',
            style: Hud.label(size: 9.5),
          ),
        ]);
      },
    );
  }
}
