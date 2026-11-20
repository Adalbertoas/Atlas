import 'package:flutter/material.dart';

import '../core/models.dart';
import '../core/session.dart';
import '../ui/theme.dart';

/// Lo que ATLAS recuerda de vos: buscar, agregar y borrar.
class MemoryView extends StatefulWidget {
  const MemoryView({super.key, required this.session});

  final Session session;

  @override
  State<MemoryView> createState() => _MemoryViewState();
}

class _MemoryViewState extends State<MemoryView> {
  final _search = TextEditingController();
  final _add = TextEditingController();
  List<Memory> _items = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _search.dispose();
    _add.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      _items = await widget.session.api.memories(query: _search.text);
      _error = null;
    } catch (error) {
      _error = '$error';
    }
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _save() async {
    final text = _add.text.trim();
    if (text.isEmpty) return;
    try {
      await widget.session.api.addMemory(text);
      _add.clear();
      await _load();
    } catch (error) {
      if (mounted) showMessage(context, '$error');
    }
  }

  Future<void> _delete(Memory memory) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('¿Olvidar esto?'),
        content: Text(memory.content),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('No')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Olvidar')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await widget.session.api.deleteMemory(memory.id);
      setState(() => _items.remove(memory));
    } catch (error) {
      if (mounted) showMessage(context, '$error');
    }
  }

  @override
  Widget build(BuildContext context) {
    return HudPanel(
      title: 'Memoria',
      icon: Icons.psychology_outlined,
      child: Column(children: [
        TextField(
          controller: _search,
          textInputAction: TextInputAction.search,
          onSubmitted: (_) => _load(),
          decoration: InputDecoration(
            hintText: 'Buscar en la memoria…',
            prefixIcon: const Icon(Icons.search),
            suffixIcon: IconButton(icon: const Icon(Icons.clear), onPressed: () {
              _search.clear();
              _load();
            }),
          ),
        ),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(
            child: TextField(
              controller: _add,
              onSubmitted: (_) => _save(),
              decoration: const InputDecoration(hintText: 'Algo que ATLAS deba recordar…', prefixIcon: Icon(Icons.bookmark_add_outlined)),
            ),
          ),
          const SizedBox(width: 8),
          FilledButton(onPressed: _save, child: const Text('Guardar')),
        ]),
        const SizedBox(height: 12),
        Expanded(
          child: _loading
              ? const Center(child: CircularProgressIndicator())
              : _error != null
                  ? Center(child: Text(_error!, style: const TextStyle(color: Hud.red)))
                  : _items.isEmpty
                      ? const Center(child: Text('Memoria vacía.', style: TextStyle(color: Hud.muted)))
                      : RefreshIndicator(
                          onRefresh: _load,
                          child: ListView.separated(
                            itemCount: _items.length,
                            separatorBuilder: (_, _) => const Divider(height: 1),
                            itemBuilder: (context, i) {
                              final m = _items[i];
                              return ListTile(
                                leading: const Icon(Icons.memory, color: Hud.cyan),
                                title: Text(m.content),
                                subtitle: Text(m.category, style: const TextStyle(color: Hud.muted)),
                                trailing: IconButton(icon: const Icon(Icons.delete_outline, color: Hud.muted), onPressed: () => _delete(m)),
                              );
                            },
                          ),
                        ),
        ),
      ]),
    );
  }
}
