import 'package:flutter/material.dart';

import '../models/routine.dart';
import '../services/api_client.dart';
import '../theme/atlas_theme.dart';
import '../widgets/atlas_chrome.dart';

/// Rutinas del Automation Engine. Solo lectura más "Ejecutar", igual que la
/// vista de automatizaciones del dashboard: crearlas se hace por chat
/// ("cuando sean las 8 apagá la luz"), que es el camino que pasa por el
/// Orchestrator.
class AutomationsScreen extends StatefulWidget {
  final ApiClient apiClient;
  const AutomationsScreen({super.key, required this.apiClient});

  @override
  State<AutomationsScreen> createState() => _AutomationsScreenState();
}

class _AutomationsScreenState extends State<AutomationsScreen> {
  List<Routine> _routines = [];
  bool _loading = true;
  String? _error;
  int? _runningId;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final routines = await widget.apiClient.listAutomations();
      if (mounted) setState(() => _routines = routines);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) setState(() => _error = 'No se pudo conectar al servidor.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _run(Routine routine) async {
    setState(() => _runningId = routine.id);
    try {
      final result = await widget.apiClient.runAutomation(routine.id);
      if (!mounted) return;
      // El resultado distingue ejecutadas de salteadas (una acción puede
      // saltarse si su herramienta pide confirmación), así que decir solo
      // "listo" ocultaría la mitad de lo que pasó.
      final parts = <String>[
        if (result.executed.isNotEmpty) '${result.executed.length} ejecutada(s)',
        if (result.skipped.isNotEmpty) '${result.skipped.length} salteada(s)',
      ];
      _snack(parts.isEmpty ? 'Sin acciones para ejecutar.' : '${routine.name}: ${parts.join(", ")}');
    } on ApiException catch (e) {
      _snack(e.message);
    } catch (_) {
      _snack('No se pudo ejecutar la rutina.');
    } finally {
      if (mounted) setState(() => _runningId = null);
    }
  }

  void _snack(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    return AtlasResourceList<Routine>(
      items: _routines,
      loading: _loading,
      error: _error,
      emptyMessage: 'Sin rutinas todavía.',
      onRefresh: _load,
      itemBuilder: (context, routine) => AtlasCard(
        icon: Icons.auto_mode_outlined,
        iconColor: routine.triggers.isEmpty ? AtlasColors.textDim : AtlasColors.accent,
        title: routine.name,
        subtitle: routine.summary,
        trailing: _runningId == routine.id
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2, color: AtlasColors.accent),
              )
            : AtlasCardButton(
                label: 'Ejecutar',
                onPressed: _runningId == null ? () => _run(routine) : null,
              ),
      ),
    );
  }
}
