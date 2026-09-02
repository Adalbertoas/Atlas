import 'package:flutter/material.dart';

import '../theme/atlas_theme.dart';

/// Piezas visuales compartidas por todas las pantallas, equivalentes a las
/// clases de dashboard/styles.css que se repiten en varias vistas
/// (`.brand-mark`, `.status-dot`, `.icon-button`, `.view-header`, `.card`).
/// Igual criterio que shared/ en el frontend web: si cada pantalla se
/// dibujara su propia tarjeta, en dos iteraciones dejarían de parecerse.

/// `.brand-mark` — el ícono de la marca con el halo de --accent-glow.
class AtlasBrandMark extends StatelessWidget {
  final double size;
  const AtlasBrandMark({super.key, this.size = 26});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        boxShadow: [
          BoxShadow(color: AtlasColors.accentGlow, blurRadius: size * 0.55, spreadRadius: -size * 0.12),
        ],
      ),
      child: Icon(Icons.hub_outlined, size: size, color: AtlasColors.accent),
    );
  }
}

/// `.status-dot` — verde/cian latiendo si el backend contesta, rojo si no,
/// gris mientras no se sabe. La animación es la misma idea que @keyframes
/// pulse: un anillo que se expande y se desvanece.
class AtlasStatusDot extends StatefulWidget {
  final bool? online; // null = todavía sin saber
  const AtlasStatusDot({super.key, required this.online});

  @override
  State<AtlasStatusDot> createState() => _AtlasStatusDotState();
}

class _AtlasStatusDotState extends State<AtlasStatusDot> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: const Duration(milliseconds: 2200))..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = switch (widget.online) {
      true => AtlasColors.accent,
      false => AtlasColors.danger,
      null => AtlasColors.textFaint,
    };

    return SizedBox(
      width: 20,
      height: 20,
      child: Center(
        child: AnimatedBuilder(
          animation: _controller,
          builder: (context, child) {
            // El anillo solo late cuando hay conexión; offline es un punto
            // rojo fijo, como en el dashboard.
            final t = widget.online == true ? Curves.easeOut.transform(_controller.value) : 0.0;
            return Container(
              width: 9,
              height: 9,
              decoration: BoxDecoration(
                color: color,
                shape: BoxShape.circle,
                boxShadow: widget.online == true
                    ? [BoxShadow(color: color.withValues(alpha: 0.35 * (1 - t)), spreadRadius: 7 * t)]
                    : null,
              ),
            );
          },
        ),
      ),
    );
  }
}

/// `.icon-button` — cuadrado con borde, sin relleno.
class AtlasIconButton extends StatelessWidget {
  final IconData icon;
  final String tooltip;
  final VoidCallback? onPressed;

  const AtlasIconButton({super.key, required this.icon, required this.tooltip, this.onPressed});

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(9),
        child: Container(
          width: 34,
          height: 34,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(9),
            border: Border.all(color: AtlasColors.borderBright),
          ),
          child: Icon(icon, size: 17, color: AtlasColors.textDim),
        ),
      ),
    );
  }
}

/// La barra superior del dashboard adaptada al celular: la marca ocupa el
/// lugar que allá tiene el `.sidebar-brand` (en una pantalla angosta no hay
/// barra lateral donde ponerla), el título de la vista va debajo, y el punto
/// de estado del `.sidebar-footer` se mueve al lado de la marca.
class AtlasTopBar extends StatelessWidget implements PreferredSizeWidget {
  final String title;
  final String subtitle;
  final bool? online;
  final List<Widget> actions;

  const AtlasTopBar({
    super.key,
    required this.title,
    required this.subtitle,
    required this.online,
    this.actions = const [],
  });

  @override
  Size get preferredSize => const Size.fromHeight(96);

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      bottom: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const AtlasBrandMark(size: 22),
                const SizedBox(width: 9),
                const Text(
                  'ATLAS',
                  style: TextStyle(
                    fontFamily: AtlasFonts.display,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 2.2,
                    color: AtlasColors.text,
                  ),
                ),
                const SizedBox(width: 6),
                AtlasStatusDot(online: online),
                const Spacer(),
                ...actions,
              ],
            ),
            const SizedBox(height: 6),
            Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontFamily: AtlasFonts.display,
                    fontSize: 22,
                    fontWeight: FontWeight.w600,
                    color: AtlasColors.text,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Text(
                      subtitle,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 12, color: AtlasColors.textFaint),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// `.card` — la fila de lista que comparten dispositivos, rutinas, avisos y
/// memoria.
class AtlasCard extends StatelessWidget {
  final IconData icon;
  final Color? iconColor;
  final String title;
  final String subtitle;
  final Widget? trailing;
  final int titleMaxLines;

  const AtlasCard({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    this.iconColor,
    this.trailing,
    this.titleMaxLines = 1,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 12),
      decoration: atlasCardDecoration(),
      child: Row(
        children: [
          Icon(icon, size: 19, color: iconColor ?? AtlasColors.textDim),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  maxLines: titleMaxLines,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: AtlasColors.text, fontSize: 14),
                ),
                const SizedBox(height: 3),
                Text(
                  subtitle,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: AtlasColors.textFaint, fontSize: 12),
                ),
              ],
            ),
          ),
          if (trailing != null) ...[const SizedBox(width: 10), trailing!],
        ],
      ),
    );
  }
}

/// El botón chico de acción dentro de una tarjeta (`.card button`).
class AtlasCardButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final bool secondary;

  const AtlasCardButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.secondary = false,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onPressed,
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
        decoration: BoxDecoration(
          color: secondary ? Colors.transparent : AtlasColors.accent,
          borderRadius: BorderRadius.circular(8),
          border: secondary ? Border.all(color: AtlasColors.borderBright) : null,
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 12.5,
            fontWeight: FontWeight.w600,
            color: secondary ? AtlasColors.textDim : AtlasColors.accentOn,
          ),
        ),
      ),
    );
  }
}

/// Lista de recursos con los cuatro estados que toda vista de lista necesita
/// (cargando, error, vacía, con datos) más "deslizar para actualizar".
/// Sin esto, las cuatro pantallas repetirían el mismo bloque de ifs y
/// terminarían mostrando el error de maneras distintas.
class AtlasResourceList<T> extends StatelessWidget {
  final List<T> items;
  final bool loading;
  final String? error;
  final String emptyMessage;
  final Future<void> Function() onRefresh;
  final Widget Function(BuildContext, T) itemBuilder;
  final Widget? header;

  const AtlasResourceList({
    super.key,
    required this.items,
    required this.loading,
    required this.error,
    required this.emptyMessage,
    required this.onRefresh,
    required this.itemBuilder,
    this.header,
  });

  @override
  Widget build(BuildContext context) {
    if (loading && items.isEmpty) {
      return const Center(child: CircularProgressIndicator(color: AtlasColors.accent));
    }
    if (error != null && items.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(error!, textAlign: TextAlign.center, style: const TextStyle(color: AtlasColors.danger)),
              const SizedBox(height: 14),
              ElevatedButton(onPressed: onRefresh, child: const Text('Reintentar')),
            ],
          ),
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: onRefresh,
      color: AtlasColors.accent,
      backgroundColor: AtlasColors.panel,
      child: items.isEmpty
          // AlwaysScrollable: sin esto una lista vacía no scrollea y el
          // gesto de "deslizar para actualizar" no llega a dispararse.
          ? ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              children: [
                ?header,
                SizedBox(height: MediaQuery.of(context).size.height * 0.25),
                Center(
                  child: Text(emptyMessage, style: const TextStyle(color: AtlasColors.textFaint)),
                ),
              ],
            )
          : ListView.separated(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.fromLTRB(14, 4, 14, 18),
              itemCount: items.length + (header == null ? 0 : 1),
              separatorBuilder: (_, _) => const SizedBox(height: 8),
              itemBuilder: (context, index) {
                if (header != null) {
                  if (index == 0) return header!;
                  return itemBuilder(context, items[index - 1]);
                }
                return itemBuilder(context, items[index]);
              },
            ),
    );
  }
}
