/// Espejo de RoutineOut (backend/app/automation/schemas.py).
class Routine {
  final int id;
  final String name;
  final List<RoutineAction> actions;
  final List<RoutineTrigger> triggers;

  Routine({
    required this.id,
    required this.name,
    required this.actions,
    required this.triggers,
  });

  factory Routine.fromJson(Map<String, dynamic> json) {
    return Routine(
      id: json['id'] as int,
      name: json['name'] as String,
      actions: (json['actions'] as List? ?? [])
          .map((e) => RoutineAction.fromJson(e as Map<String, dynamic>))
          .toList(),
      triggers: (json['triggers'] as List? ?? [])
          .map((e) => RoutineTrigger.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }

  /// Resumen de una línea para la tarjeta, con el mismo criterio que
  /// renderAutomationRow en dashboard/app.js: cuántos pasos y cómo se
  /// dispara, sin desplegar la configuración entera.
  String get summary {
    final steps = '${actions.length} ${actions.length == 1 ? "acción" : "acciones"}';
    if (triggers.isEmpty) return '$steps · manual';
    return '$steps · ${triggers.map((t) => t.label).join(", ")}';
  }
}

class RoutineAction {
  final String toolName;
  final Map<String, dynamic> params;

  RoutineAction({required this.toolName, required this.params});

  factory RoutineAction.fromJson(Map<String, dynamic> json) {
    return RoutineAction(
      toolName: json['tool_name'] as String,
      params: (json['params'] as Map?)?.cast<String, dynamic>() ?? const {},
    );
  }
}

class RoutineTrigger {
  final String type; // "SCHEDULE" | "DEVICE_STATE"
  final Map<String, dynamic> config;

  RoutineTrigger({required this.type, required this.config});

  factory RoutineTrigger.fromJson(Map<String, dynamic> json) {
    return RoutineTrigger(
      type: json['type'] as String,
      config: (json['config'] as Map?)?.cast<String, dynamic>() ?? const {},
    );
  }

  String get label {
    switch (type) {
      case 'SCHEDULE':
        final at = config['at'] ?? config['time'] ?? config['cron'];
        return at == null ? 'por horario' : 'a las $at';
      case 'DEVICE_STATE':
        return 'por estado de un dispositivo';
      default:
        return type.toLowerCase();
    }
  }
}

/// Espejo de RoutineRunResult — lo que devuelve POST /automations/{id}/run.
class RoutineRunResult {
  final String routineName;
  final List<String> executed;
  final List<String> skipped;

  RoutineRunResult({required this.routineName, required this.executed, required this.skipped});

  factory RoutineRunResult.fromJson(Map<String, dynamic> json) {
    return RoutineRunResult(
      routineName: json['routine_name'] as String? ?? '',
      executed: (json['executed'] as List? ?? []).cast<String>(),
      skipped: (json['skipped'] as List? ?? []).cast<String>(),
    );
  }
}
