import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' show PointMode;

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

import '../core/session.dart';
import 'theme.dart';

/// Fondo del escritorio: degradado, rejilla que se desvanece hacia los bordes,
/// retícula de anillos que giran muy despacio y viñeta (Hud.tsx + jarvis.css).
class HudBackdrop extends StatefulWidget {
  const HudBackdrop({super.key, this.center = const Alignment(0.1, -0.16)});

  final Alignment center;

  @override
  State<HudBackdrop> createState() => _HudBackdropState();
}

class _HudBackdropState extends State<HudBackdrop> {
  final _clock = Stopwatch()..start();
  late final Timer _timer;
  final _time = ValueNotifier<double>(0);

  @override
  void initState() {
    super.initState();
    // Los anillos tardan minutos en dar la vuelta: 20 cuadros por segundo sobran
    // y ahorran batería.
    _timer = Timer.periodic(const Duration(milliseconds: 50), (_) => _time.value = _clock.elapsedMilliseconds / 1000);
  }

  @override
  void dispose() {
    _timer.cancel();
    _time.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      child: CustomPaint(painter: _BackdropPainter(_time, widget.center), size: Size.infinite),
    );
  }
}

class _BackdropPainter extends CustomPainter {
  _BackdropPainter(this.time, this.center) : super(repaint: time);

  final ValueNotifier<double> time;
  final Alignment center;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final c = center.alongSize(size);
    canvas.drawRect(
      rect,
      Paint()
        ..shader = RadialGradient(
          center: center,
          radius: 0.9,
          colors: const [Color(0xFF04263D), Color(0xFF021422), Color(0xFF01070E)],
          stops: const [0, .45, 1],
        ).createShader(rect),
    );

    // Rejilla de 56 px enmascarada por un óvalo (más visible al centro).
    final grid = Paint()..color = const Color(0x0D3FE6FF);
    final rx = size.width * .6, ry = size.height * .6;
    for (var x = 0.0; x < size.width; x += 56) {
      for (var y = 0.0; y < size.height; y += 56) {
        final d = math.sqrt(math.pow((x - c.dx) / rx, 2) + math.pow((y - c.dy) / ry, 2));
        if (d > 1) continue;
        final a = (1 - d).clamp(0.0, 1.0);
        grid.color = Color.fromRGBO(63, 230, 255, .055 * a);
        canvas.drawLine(Offset(x, y), Offset(x + 56, y), grid);
        canvas.drawLine(Offset(x, y), Offset(x, y + 56), grid);
      }
    }

    // Retícula: anillos con marcas que giran a distintas velocidades.
    final t = time.value;
    final r = math.min(size.width, size.height * 1.18) * .5;
    final stroke = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1
      ..color = const Color(0x473FE6FF);
    void ring(double radius, double turnSeconds, void Function(Paint p) draw, {double alpha = 1}) {
      canvas.save();
      canvas.translate(c.dx, c.dy);
      canvas.rotate(2 * math.pi * t / turnSeconds);
      stroke.color = Color.fromRGBO(63, 230, 255, .28 * alpha);
      draw(stroke);
      canvas.restore();
    }

    void ticks(Paint p, int count, double radius, double long, double short, int every) {
      for (var i = 0; i < count; i++) {
        final a = i / count * 2 * math.pi;
        final len = i % every == 0 ? long : short;
        final dir = Offset(math.cos(a), math.sin(a));
        canvas.drawLine(dir * radius, dir * (radius - len), p);
      }
    }

    void dashed(Paint p, double radius, List<double> pattern) {
      final circumference = 2 * math.pi * radius;
      var pos = 0.0, i = 0;
      while (pos < circumference) {
        final len = pattern[i % pattern.length];
        if (i.isEven) {
          canvas.drawArc(Rect.fromCircle(center: Offset.zero, radius: radius), pos / radius, len / radius, false, p);
        }
        pos += len;
        i++;
      }
    }

    final k = r / 500; // la retícula del escritorio mide 1040 unidades
    ring(500 * k, 120, (p) {
      ticks(p, 180, 500 * k, 16 * k, 6 * k, 15);
      canvas.drawCircle(Offset.zero, 500 * k, p);
    });
    ring(455 * k, -80, (p) => dashed(p, 455 * k, [2 * k, 10 * k]));
    ring(410 * k, 46, (p) {
      p.strokeWidth = 2;
      dashed(p, 410 * k, [220 * k, 60 * k, 40 * k, 60 * k, 120 * k, 320 * k]);
      p.strokeWidth = 1;
    });
    ring(340 * k, -160, (p) => ticks(p, 72, 340 * k, 12 * k, 5 * k, 6), alpha: .7);
    canvas.save();
    canvas.translate(c.dx, c.dy);
    canvas.rotate(2 * math.pi * t / 30);
    dashed(
      Paint()
        ..style = PaintingStyle.stroke
        ..color = const Color(0x40FFB547),
      270 * k,
      [90 * k, 30 * k],
    );
    canvas.restore();

    // Viñeta.
    canvas.drawRect(
      rect,
      Paint()
        ..shader = RadialGradient(
          center: center,
          radius: 1,
          colors: const [Colors.transparent, Color(0xBF01060C)],
          stops: const [.45, 1],
        ).createShader(rect),
    );
  }

  @override
  bool shouldRepaint(_BackdropPainter old) => false;
}

/// Neural Core: esfera de partículas que respira en reposo, se abre al
/// escuchar, gira rápido al pensar y late con la voz al hablar.
class NeuralCore extends StatefulWidget {
  const NeuralCore({super.key, required this.session, this.size = 220, this.particles = 520, this.showRings = true});

  final Session session;
  final double size;
  final int particles;
  final bool showRings;

  @override
  State<NeuralCore> createState() => _NeuralCoreState();
}

class _NeuralCoreState extends State<NeuralCore> with SingleTickerProviderStateMixin {
  late final Ticker _ticker;
  final _time = ValueNotifier<double>(0);
  late List<_Particle> _points;
  double _level = 0;
  double _energy = 0;

  @override
  void initState() {
    super.initState();
    _points = _sphere(widget.particles);
    _ticker = createTicker((elapsed) {
      // Suaviza el nivel (sube rápido, baja despacio) para que no tiemble.
      final target = widget.session.coreLevel;
      _level += (target - _level) * (target > _level ? .45 : .12);
      final mode = widget.session.coreMode;
      final goal = switch (mode) {
        CoreMode.idle => 0.0,
        CoreMode.listening => .5,
        CoreMode.thinking => 1.0,
        CoreMode.speaking => .7,
        CoreMode.error => .2,
      };
      _energy += (goal - _energy) * .05;
      _time.value = elapsed.inMicroseconds / 1e6;
    })..start();
  }

  @override
  void didUpdateWidget(NeuralCore old) {
    super.didUpdateWidget(old);
    if (old.particles != widget.particles) _points = _sphere(widget.particles);
  }

  @override
  void dispose() {
    _ticker.dispose();
    _time.dispose();
    super.dispose();
  }

  static List<_Particle> _sphere(int n) {
    final random = math.Random(7);
    final golden = math.pi * (3 - math.sqrt(5));
    return [
      for (var i = 0; i < n; i++)
        () {
          final y = 1 - (i / (n - 1)) * 2;
          final radius = math.sqrt(1 - y * y);
          final theta = golden * i;
          return _Particle(math.cos(theta) * radius, y, math.sin(theta) * radius, random.nextDouble() * math.pi * 2, .6 + random.nextDouble() * .8);
        }(),
    ];
  }

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      child: SizedBox.square(
        dimension: widget.size,
        child: CustomPaint(
          painter: _CorePainter(
            time: _time,
            points: _points,
            mode: () => widget.session.coreMode,
            level: () => _level,
            energy: () => _energy,
            rings: widget.showRings,
          ),
        ),
      ),
    );
  }
}

class _Particle {
  _Particle(this.x, this.y, this.z, this.phase, this.size);

  final double x, y, z, phase, size;
}

class _CorePainter extends CustomPainter {
  _CorePainter({required this.time, required this.points, required this.mode, required this.level, required this.energy, required this.rings})
      : super(repaint: time);

  final ValueNotifier<double> time;
  final List<_Particle> points;
  final CoreMode Function() mode;
  final double Function() level;
  final double Function() energy;
  final bool rings;

  @override
  void paint(Canvas canvas, Size size) {
    final t = time.value;
    final m = mode();
    final lv = level();
    final en = energy();
    final c = size.center(Offset.zero);
    final base = size.shortestSide * .34;
    final color = switch (m) {
      CoreMode.error => Hud.red,
      CoreMode.thinking => Color.lerp(Hud.cyan, Hud.amber, .35 + .25 * math.sin(t * 3))!,
      CoreMode.speaking => Color.lerp(Hud.cyan, Colors.white, .35)!,
      _ => Hud.cyan,
    };

    // Halo.
    final glowR = base * (1.25 + .25 * lv + .1 * en);
    canvas.drawCircle(
      c,
      glowR,
      Paint()
        ..shader = RadialGradient(colors: [
          color.withValues(alpha: .28 + .25 * lv),
          color.withValues(alpha: .08),
          Colors.transparent,
        ], stops: const [0, .45, 1])
            .createShader(Rect.fromCircle(center: c, radius: glowR)),
    );

    // Anillos orbitales.
    if (rings) {
      final ring = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1
        ..color = color.withValues(alpha: .35);
      for (final (radius, speed, sweep) in [(1.32, .25, 4.6), (1.18, -.4, 2.2), (1.46, .12, 1.4)]) {
        final rr = base * radius * (1 + .06 * lv);
        canvas.drawArc(Rect.fromCircle(center: c, radius: rr), t * speed * (1 + en * 2), sweep, false, ring);
        canvas.drawArc(Rect.fromCircle(center: c, radius: rr), t * speed * (1 + en * 2) + math.pi, sweep * .4, false, ring);
      }
    }

    // Partículas en una esfera que gira; profundidad = tamaño y brillo.
    final spin = t * (.22 + en * 1.1);
    final tilt = .42 + .08 * math.sin(t * .3);
    final cosS = math.cos(spin), sinS = math.sin(spin), cosT = math.cos(tilt), sinT = math.sin(tilt);
    final buckets = List.generate(4, (_) => <Offset>[]);
    final sizes = [1.0, 1.5, 2.1, 2.8];
    for (final p in points) {
      final wobble = 1 + .045 * math.sin(t * 1.6 + p.phase) + lv * .22 * math.sin(t * 9 + p.phase * 3) + .03 * en * math.sin(t * 5 + p.phase);
      final breath = 1 + .025 * math.sin(t * .9);
      var x = p.x * wobble * breath, y = p.y * wobble * breath, z = p.z * wobble * breath;
      // Giro en Y y luego inclinación en X.
      final x1 = x * cosS + z * sinS;
      final z1 = -x * sinS + z * cosS;
      final y1 = y * cosT - z1 * sinT;
      final z2 = y * sinT + z1 * cosT;
      x = x1;
      y = y1;
      z = z2;
      final perspective = 1.6 / (2.6 - z);
      final pos = c + Offset(x, y) * base * perspective * (1 + .12 * lv);
      final depth = ((z + 1) / 2 * 3.99).floor().clamp(0, 3);
      buckets[depth].add(pos);
    }
    for (var i = 0; i < 4; i++) {
      canvas.drawPoints(
        PointMode.points,
        buckets[i],
        Paint()
          ..color = color.withValues(alpha: .25 + i * .22)
          ..strokeWidth = sizes[i]
          ..strokeCap = StrokeCap.round,
      );
    }

    // Núcleo brillante.
    final coreR = base * (.16 + .08 * lv + .03 * math.sin(t * 2));
    canvas.drawCircle(
      c,
      coreR * 2.2,
      Paint()
        ..shader = RadialGradient(colors: [Colors.white.withValues(alpha: .95), color.withValues(alpha: .55), Colors.transparent], stops: const [0, .35, 1])
            .createShader(Rect.fromCircle(center: c, radius: coreR * 2.2)),
    );
  }

  @override
  bool shouldRepaint(_CorePainter old) => true;
}

/// Mini reactor del perfil (barra superior): tres anillos que giran; más
/// rápido mientras ATLAS habla. Gris si no hay conexión.
class ProfileOrb extends StatefulWidget {
  const ProfileOrb({super.key, required this.online, required this.speaking, this.size = 38});

  final bool online;
  final bool speaking;
  final double size;

  @override
  State<ProfileOrb> createState() => _ProfileOrbState();
}

class _ProfileOrbState extends State<ProfileOrb> with SingleTickerProviderStateMixin {
  late final _controller = AnimationController(vsync: this, duration: const Duration(seconds: 36))..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      child: SizedBox.square(
        dimension: widget.size,
        child: CustomPaint(painter: _ProfileOrbPainter(_controller, widget.online, widget.speaking)),
      ),
    );
  }
}

class _ProfileOrbPainter extends CustomPainter {
  _ProfileOrbPainter(this.animation, this.online, this.speaking) : super(repaint: animation);

  final Animation<double> animation;
  final bool online;
  final bool speaking;

  @override
  void paint(Canvas canvas, Size size) {
    final c = size.center(Offset.zero);
    final r = size.shortestSide / 2;
    final base = online ? Hud.cyan : Hud.dim;
    canvas.drawCircle(
      c,
      r * .6,
      Paint()
        ..shader = RadialGradient(colors: [
          online ? const Color(0xFFE4FDFF) : Hud.muted,
          base,
          base.withValues(alpha: .35),
          Colors.transparent,
        ], stops: const [0, .23, .6, 1])
            .createShader(Rect.fromCircle(center: c, radius: r * .6)),
    );
    final speed = speaking ? 5.0 : 1.0;
    final turns = animation.value * 2 * math.pi * speed;
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;
    paint.color = base.withValues(alpha: .6);
    for (final start in [0.0, math.pi]) {
      canvas.drawArc(Rect.fromCircle(center: c, radius: r * .9), turns * 6 + start, math.pi * .55, false, paint);
    }
    paint.color = base.withValues(alpha: .45);
    for (final start in [math.pi / 2, math.pi * 1.5]) {
      canvas.drawArc(Rect.fromCircle(center: c, radius: r * .66), -turns * 9 + start, math.pi * .55, false, paint);
    }
    paint.color = base.withValues(alpha: .25);
    for (var i = 0; i < 24; i++) {
      final a = turns * 2 + i / 24 * 2 * math.pi;
      canvas.drawArc(Rect.fromCircle(center: c, radius: r * 1.0), a, .12, false, paint);
    }
  }

  @override
  bool shouldRepaint(_ProfileOrbPainter old) => old.online != online || old.speaking != speaking;
}

/// Medidor segmentado de 10 bloques (CPU/RAM). Ámbar al 75 %, rojo al 90 %.
class HudMeter extends StatelessWidget {
  const HudMeter({super.key, required this.label, required this.value});

  final String label;
  final double? value;

  @override
  Widget build(BuildContext context) {
    final v = value;
    final lit = v == null ? 0 : (v.clamp(0, 100) / 10).round();
    final color = v == null || v < 75 ? Hud.cyan : (v < 90 ? Hud.amber : Hud.red);
    return Row(mainAxisSize: MainAxisSize.min, children: [
      SizedBox(width: 30, child: Text(label, style: Hud.label(size: 9.5))),
      for (var i = 0; i < 10; i++)
        Transform(
          transform: Matrix4.skewX(-.3),
          child: Container(
            width: 5,
            height: 8,
            margin: const EdgeInsets.only(right: 2),
            decoration: BoxDecoration(
              color: i < lit ? color : const Color(0x1F3FE6FF),
              boxShadow: i < lit ? [BoxShadow(color: color.withValues(alpha: .7), blurRadius: 5)] : null,
            ),
          ),
        ),
      const SizedBox(width: 5),
      SizedBox(
        width: 32,
        child: Text(v == null ? '--' : '${v.round()}%', textAlign: TextAlign.right, style: Hud.label(size: 9.5, color: Hud.text)),
      ),
    ]);
  }
}
