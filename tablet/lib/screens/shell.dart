import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../core/hands_free.dart';
import '../core/models_extra.dart';
import '../core/session.dart';
import '../ui/hud_art.dart';
import '../ui/theme.dart';
import 'actions_view.dart';
import 'activity_view.dart';
import 'chat_view.dart';
import 'core_view.dart';
import 'devices_view.dart';
import 'memory_view.dart';
import 'settings_view.dart';
import 'today_view.dart';
import 'voice_controls.dart';

enum Page { chat, today, actions, home, memory, activity, settings }

/// Misma estructura que el escritorio: barra lateral con las secciones, barra
/// superior con reloj y telemetría de la PC, y el fondo HUD detrás de todo.
class Shell extends StatefulWidget {
  const Shell({super.key, required this.session, required this.onDisconnect});

  final Session session;
  final VoidCallback onDisconnect;

  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> with WidgetsBindingObserver {
  Page _page = Page.chat;
  bool _collapsed = false;
  PcStatus? _pc;
  bool _online = true;
  int _unread = 0;
  Timer? _poll;

  static const _nav = [
    (Page.chat, Icons.forum_outlined, 'Chat'),
    (Page.today, Icons.home_outlined, 'Hoy'),
    (Page.actions, Icons.handyman_outlined, 'Acciones'),
    (Page.home, Icons.lightbulb_outline, 'Casa'),
    (Page.memory, Icons.view_in_ar_outlined, 'Memoria'),
    (Page.activity, Icons.blur_on, 'Actividad'),
    (Page.settings, Icons.settings_outlined, 'Configuración'),
  ];

  Session get _session => widget.session;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // Pantalla completa, como una estación: sin barras de Android.
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
    unawaited(_session.start());
    _refresh();
    _poll = Timer.periodic(const Duration(seconds: 5), (_) => _refresh());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _poll?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused) unawaited(_session.engine.pauseForBackground());
    if (state == AppLifecycleState.resumed) {
      SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
      unawaited(_session.engine.resumeFromBackground());
    }
  }

  int _tick = 0;

  Future<void> _refresh() async {
    try {
      final pc = await _session.api.systemStatus();
      // Avisos nuevos cada 30 s; CPU/RAM cada 5 s.
      final unread = _tick++ % 6 == 0 ? (await _session.api.notifications()).where((n) => !n.read).length : _unread;
      if (mounted) {
        setState(() {
          _pc = pc;
          _online = true;
          _unread = unread;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _pc = null;
          _online = false;
        });
      }
    }
  }

  /// Desde los paneles. Si el pedido termina en espacio ("Recuérdame "), se deja
  /// en el cuadro de texto para completarlo.
  void _ask(String prompt) {
    setState(() => _page = Page.chat);
    if (prompt.trim().isEmpty) return; // solo mostrar el chat
    if (prompt.endsWith(' ')) {
      _session.chat.draft.value = prompt;
    } else {
      unawaited(_session.chat.send(prompt));
    }
  }

  void _openCore() {
    Navigator.of(context).push(PageRouteBuilder<void>(
      opaque: true,
      transitionDuration: const Duration(milliseconds: 350),
      pageBuilder: (_, _, _) => CoreView(session: _session),
      transitionsBuilder: (_, animation, _, child) => FadeTransition(opacity: animation, child: child),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Hud.background,
      body: Stack(children: [
        const Positioned.fill(child: HudBackdrop()),
        LayoutBuilder(builder: (context, constraints) {
          final narrow = constraints.maxWidth < 800;
          final collapsed = _collapsed || narrow;
          return Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            _Sidebar(
              session: _session,
              items: _nav,
              page: _page,
              collapsed: collapsed,
              canCollapse: !narrow,
              onSelect: (p) => setState(() => _page = p),
              onToggleCollapse: () => setState(() => _collapsed = !_collapsed),
              onOpenCore: _openCore,
            ),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                _TopBar(
                  session: _session,
                  pc: _pc,
                  online: _online,
                  unread: _unread,
                  compact: constraints.maxWidth < 900,
                  onAsk: _ask,
                  onBell: () => setState(() => _page = Page.today),
                  onSettings: () => setState(() => _page = Page.settings),
                ),
                Expanded(child: Padding(padding: const EdgeInsets.fromLTRB(12, 10, 12, 12), child: _content(constraints.maxWidth))),
              ]),
            ),
          ]);
        }),
      ]),
    );
  }

  Widget _content(double width) {
    final session = _session;
    return switch (_page) {
      Page.chat => width >= 880
          ? Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              Expanded(child: ChatView(session: session, onOpenCore: _openCore)),
              const SizedBox(width: 12),
              SizedBox(
                width: 268,
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  ActionsView(session: session, onAsk: _ask, compact: true),
                  const SizedBox(height: 12),
                  Expanded(child: TodayView(session: session, onAsk: _ask, compact: true)),
                ]),
              ),
            ])
          : ChatView(session: session, onOpenCore: _openCore),
      Page.today => TodayView(session: session, onAsk: _ask),
      Page.actions => ActionsView(session: session, onAsk: _ask),
      Page.home => DevicesView(session: session, onAsk: _ask),
      Page.memory => MemoryView(session: session),
      Page.activity => ActivityView(session: session),
      Page.settings => SettingsView(session: session, onDisconnect: widget.onDisconnect),
    };
  }
}

class _Sidebar extends StatelessWidget {
  const _Sidebar({
    required this.session,
    required this.items,
    required this.page,
    required this.collapsed,
    required this.canCollapse,
    required this.onSelect,
    required this.onToggleCollapse,
    required this.onOpenCore,
  });

  final Session session;
  final List<(Page, IconData, String)> items;
  final Page page;
  final bool collapsed;
  final bool canCollapse;
  final ValueChanged<Page> onSelect;
  final VoidCallback onToggleCollapse;
  final VoidCallback onOpenCore;

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 220),
      width: collapsed ? 64 : 172,
      decoration: const BoxDecoration(
        gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Color(0xF0020B14), Color(0xF501070D)]),
        border: Border(right: BorderSide(color: Hud.line)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Container(
          height: 60,
          padding: EdgeInsets.symmetric(horizontal: collapsed ? 0 : 16),
          decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Hud.line))),
          child: Row(mainAxisAlignment: collapsed ? MainAxisAlignment.center : MainAxisAlignment.start, children: [
            Text('‹', style: TextStyle(fontSize: 28, color: Hud.cyan, height: 1, shadows: Hud.glow)),
            if (!collapsed) ...[
              const SizedBox(width: 10),
              Expanded(
                child: ValueListenableBuilder(
                  valueListenable: session.assistantName,
                  builder: (_, name, _) => Text(
                    name.toUpperCase(),
                    maxLines: 1,
                    overflow: TextOverflow.fade,
                    softWrap: false,
                    style: TextStyle(
                      fontFamily: Hud.display,
                      fontWeight: FontWeight.w700,
                      fontSize: name.length > 5 ? 19 : 24,
                      letterSpacing: name.length > 5 ? 4 : 7,
                      color: Hud.bright,
                      shadows: const [Shadow(color: Color(0x993FE6FF), blurRadius: 14)],
                    ),
                  ),
                ),
              ),
            ],
          ]),
        ),
        Expanded(
          child: ListView(padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 8), children: [
            for (final (id, icon, label) in items)
              _NavButton(icon: icon, label: label, active: page == id, collapsed: collapsed, onTap: () => onSelect(id)),
          ]),
        ),
        ListenableBuilder(
          listenable: session.core,
          builder: (context, _) => _VoiceBlock(session: session, collapsed: collapsed, onOpenCore: onOpenCore),
        ),
        if (canCollapse)
          InkWell(
            onTap: onToggleCollapse,
            child: Container(
              height: 40,
              alignment: collapsed ? Alignment.center : Alignment.centerLeft,
              padding: EdgeInsets.symmetric(horizontal: collapsed ? 0 : 18),
              decoration: const BoxDecoration(border: Border(top: BorderSide(color: Hud.line))),
              child: Text(collapsed ? '›' : '‹  CONTRAER', style: Hud.title(size: 12, color: Hud.dim, weight: FontWeight.w600)),
            ),
          ),
      ]),
    );
  }
}

class _NavButton extends StatelessWidget {
  const _NavButton({required this.icon, required this.label, required this.active, required this.collapsed, required this.onTap});

  final IconData icon;
  final String label;
  final bool active;
  final bool collapsed;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final content = Container(
      height: 44,
      margin: const EdgeInsets.only(bottom: 4),
      padding: EdgeInsets.symmetric(horizontal: collapsed ? 0 : 12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(4),
        gradient: active ? const LinearGradient(colors: [Color(0x293FE6FF), Color(0x053FE6FF)], stops: [0, .85]) : null,
      ),
      child: Stack(children: [
        if (active)
          Positioned(
            left: collapsed ? 0 : -12,
            top: 8,
            bottom: 8,
            child: Container(width: 2, decoration: const BoxDecoration(color: Hud.cyan, boxShadow: [BoxShadow(color: Hud.cyan, blurRadius: 10)])),
          ),
        Row(mainAxisAlignment: collapsed ? MainAxisAlignment.center : MainAxisAlignment.start, children: [
          Icon(icon, size: 19, color: active ? Hud.cyan : Hud.dim, shadows: active ? Hud.glow : null),
          if (!collapsed) ...[
            const SizedBox(width: 12),
            Expanded(
              child: Text(label.toUpperCase(),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontFamily: Hud.display,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    letterSpacing: .6,
                    color: active ? Hud.bright : Hud.muted,
                  )),
            ),
          ],
        ]),
      ]),
    );
    return Tooltip(
      message: collapsed ? label : '',
      child: InkWell(borderRadius: BorderRadius.circular(4), onTap: onTap, child: content),
    );
  }
}

/// Estado de la voz (como los indicadores del Neural Core del escritorio).
class _VoiceBlock extends StatelessWidget {
  const _VoiceBlock({required this.session, required this.collapsed, required this.onOpenCore});

  final Session session;
  final bool collapsed;
  final VoidCallback onOpenCore;

  @override
  Widget build(BuildContext context) {
    final engine = session.engine;
    final listening = engine.handsFree;
    final mode = session.coreMode;
    final dot = switch (mode) {
      CoreMode.listening => Hud.green,
      CoreMode.thinking => Hud.amber,
      CoreMode.speaking => Hud.cyan,
      CoreMode.error => Hud.red,
      CoreMode.idle => engine.phase == ListenPhase.standby ? Hud.green : Hud.dim,
    };
    if (collapsed) {
      return Column(children: [
        IconButton(
          tooltip: 'Escuchar "Atlas"',
          onPressed: () => toggleHandsFree(context, session),
          icon: Icon(listening ? Icons.hearing : Icons.hearing_disabled, color: listening ? Hud.cyan : Hud.dim),
        ),
        IconButton(tooltip: 'Ver núcleo', onPressed: onOpenCore, icon: const Icon(Icons.blur_circular, color: Hud.cyan)),
        const SizedBox(height: 6),
      ]);
    }
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
      decoration: const BoxDecoration(border: Border(top: BorderSide(color: Hud.line))),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        InkWell(
          onTap: onOpenCore,
          child: Row(children: [
            NeuralCore(session: session, size: 34, particles: 110, showRings: false),
            const SizedBox(width: 8),
            Container(width: 7, height: 7, decoration: BoxDecoration(color: dot, shape: BoxShape.circle, boxShadow: [BoxShadow(color: dot, blurRadius: 6)])),
            const SizedBox(width: 6),
            Expanded(child: Text(session.statusLabel.toUpperCase(), maxLines: 1, overflow: TextOverflow.ellipsis, style: Hud.label(size: 9.5, color: Hud.text))),
          ]),
        ),
        const SizedBox(height: 10),
        HudChip(
          label: 'ESCUCHAR "ATLAS"',
          icon: listening ? Icons.hearing : Icons.hearing_disabled,
          selected: listening,
          onTap: () => toggleHandsFree(context, session),
        ),
        const SizedBox(height: 6),
        HudChip(label: 'VER NÚCLEO', icon: Icons.blur_circular, onTap: onOpenCore),
      ]),
    );
  }
}

class _TopBar extends StatefulWidget {
  const _TopBar({
    required this.session,
    required this.pc,
    required this.online,
    required this.unread,
    required this.compact,
    required this.onAsk,
    required this.onBell,
    required this.onSettings,
  });

  final Session session;
  final PcStatus? pc;
  final bool online;
  final int unread;
  final bool compact;
  final ValueChanged<String> onAsk;
  final VoidCallback onBell;
  final VoidCallback onSettings;

  @override
  State<_TopBar> createState() => _TopBarState();
}

class _TopBarState extends State<_TopBar> {
  final _search = TextEditingController();
  late final Timer _clock;
  DateTime _now = DateTime.now();

  @override
  void initState() {
    super.initState();
    _clock = Timer.periodic(const Duration(seconds: 1), (_) => setState(() => _now = DateTime.now()));
  }

  @override
  void dispose() {
    _clock.cancel();
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    const days = ['LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB', 'DOM'];
    const months = ['ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC'];
    String two(int v) => v.toString().padLeft(2, '0');
    final time = '${two(_now.hour)}:${two(_now.minute)}:${two(_now.second)}';
    final date = '${days[_now.weekday - 1]}, ${two(_now.day)} ${months[_now.month - 1]}';
    return Container(
      height: 60,
      padding: const EdgeInsets.symmetric(horizontal: 18),
      decoration: const BoxDecoration(
        gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Color(0xE6020C15), Color(0x9E020C15)]),
        border: Border(bottom: BorderSide(color: Hud.line)),
      ),
      child: Row(children: [
        Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(time,
              style: const TextStyle(
                fontFamily: Hud.mono,
                fontSize: 19,
                letterSpacing: 1.1,
                color: Hud.bright,
                fontFeatures: [FontFeature.tabularFigures()],
                shadows: [Shadow(color: Color(0x8C3FE6FF), blurRadius: 12)],
              )),
          Text(date, style: Hud.title(size: 11, color: Hud.muted, weight: FontWeight.w600)),
        ]),
        if (!widget.compact) ...[
          Container(width: 1, height: 30, margin: const EdgeInsets.symmetric(horizontal: 16), color: Hud.line),
          Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
            HudMeter(label: 'CPU', value: widget.pc?.cpu),
            const SizedBox(height: 5),
            HudMeter(label: 'RAM', value: widget.pc?.ram),
          ]),
        ],
        const SizedBox(width: 16),
        Expanded(
          child: Align(
            alignment: Alignment.center,
            child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 420), child: _searchBox()),
          ),
        ),
        const SizedBox(width: 12),
        Stack(clipBehavior: Clip.none, children: [
          IconButton(tooltip: 'Avisos', onPressed: widget.onBell, icon: const Icon(Icons.notifications_none, color: Hud.muted)),
          if (widget.unread > 0)
            Positioned(
              right: 6,
              top: 6,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                decoration: BoxDecoration(color: Hud.amber, borderRadius: BorderRadius.circular(8)),
                child: Text('${widget.unread}', style: const TextStyle(fontSize: 10, color: Colors.black, fontWeight: FontWeight.w700)),
              ),
            ),
        ]),
        IconButton(tooltip: 'Configuración', onPressed: widget.onSettings, icon: const Icon(Icons.settings_outlined, color: Hud.muted)),
        const SizedBox(width: 6),
        ValueListenableBuilder(
          valueListenable: widget.session.voice.isSpeaking,
          builder: (_, speaking, _) => ProfileOrb(online: widget.online, speaking: speaking),
        ),
        if (!widget.compact) ...[
          const SizedBox(width: 10),
          Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
            ValueListenableBuilder(
              valueListenable: widget.session.assistantName,
              builder: (_, name, _) => Text(name.toUpperCase(), style: Hud.title(size: 14, weight: FontWeight.w700)),
            ),
            Row(children: [
              Container(
                width: 6,
                height: 6,
                decoration: BoxDecoration(
                  color: widget.online ? Hud.green : Hud.red,
                  shape: BoxShape.circle,
                  boxShadow: [BoxShadow(color: widget.online ? Hud.green : Hud.red, blurRadius: 6)],
                ),
              ),
              const SizedBox(width: 5),
              Text(widget.online ? 'En línea' : 'Sin conexión', style: Hud.label(size: 9.5)),
            ]),
          ]),
        ],
      ]),
    );
  }

  Widget _searchBox() {
    return ClipPath(
      clipper: const _CutCorners(12),
      child: Container(
        height: 38,
        decoration: BoxDecoration(color: const Color(0xB303121F), border: Border.all(color: Hud.line2)),
        padding: const EdgeInsets.symmetric(horizontal: 12),
        child: Row(children: [
          const Icon(Icons.search, size: 18, color: Hud.cyan),
          const SizedBox(width: 8),
          Expanded(
            child: TextField(
              controller: _search,
              style: const TextStyle(fontSize: 13),
              textInputAction: TextInputAction.send,
              decoration: const InputDecoration(
                isCollapsed: true,
                filled: false,
                border: InputBorder.none,
                enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none,
                hintText: 'Buscar, preguntar o ejecutar un comando...',
              ),
              onSubmitted: (value) {
                if (value.trim().isEmpty) return;
                widget.onAsk(value.trim());
                _search.clear();
              },
            ),
          ),
        ]),
      ),
    );
  }
}

/// Esquinas cortadas en diagonal (clip-path del buscador del escritorio).
class _CutCorners extends CustomClipper<Path> {
  const _CutCorners(this.cut);

  final double cut;

  @override
  Path getClip(Size size) => Path()
    ..moveTo(cut, 0)
    ..lineTo(size.width, 0)
    ..lineTo(size.width, size.height - cut)
    ..lineTo(size.width - cut, size.height)
    ..lineTo(0, size.height)
    ..lineTo(0, cut)
    ..close();

  @override
  bool shouldReclip(_CutCorners old) => old.cut != cut;
}
