import 'package:flutter/material.dart';

import '../models/memory_entry.dart';
import '../services/api_client.dart';
import '../theme/atlas_theme.dart';
import '../utils/format.dart';
import '../widgets/atlas_chrome.dart';

/// Lo que ATLAS recuerda de vos. Se puede leer y olvidar, no escribir a
/// mano: las memorias las crea el modelo durante la conversación (igual que
/// en el dashboard, donde esta vista tampoco tiene un formulario de alta).
class MemoryScreen extends StatefulWidget {
  final ApiClient apiClient;
  const MemoryScreen({super.key, required this.apiClient});

  @override
  State<MemoryScreen> createState() => _MemoryScreenState();
}

class _MemoryScreenState extends State<MemoryScreen> {
  List<MemoryEntry> _entries = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _error = null);
    try {
      final entries = await widget.apiClient.listMemories();
      if (mounted) setState(() => _entries = entries);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) setState(() => _error = 'No se pudo conectar al servidor.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _forget(MemoryEntry entry) async {
    // Borrar una memoria no se deshace, así que se pregunta — mismo criterio
    // que el confirm() del dashboard antes de DELETE /memory/{id}.
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AtlasColors.panel2,
        title: const Text('Olvidar esto', style: TextStyle(color: AtlasColors.text, fontSize: 17)),
        content: Text(entry.content, style: const TextStyle(color: AtlasColors.textDim)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')),
          ElevatedButton(onPressed: () => Navigator.pop(context, true), child: const Text('Olvidar')),
        ],
      ),
    );
    if (confirmed != true) return;

    try {
      await widget.apiClient.deleteMemory(entry.id);
      await _load();
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    return AtlasResourceList<MemoryEntry>(
      items: _entries,
      loading: _loading,
      error: _error,
      emptyMessage: 'ATLAS todavía no recuerda nada.',
      onRefresh: _load,
      itemBuilder: (context, entry) => AtlasCard(
        icon: Icons.psychology_outlined,
        iconColor: AtlasColors.accent,
        title: entry.content,
        titleMaxLines: 3,
        subtitle: [
          entry.category,
          if (entry.tags.isNotEmpty) entry.tags.join(', '),
          formatShortDate(entry.createdAt),
        ].join(' · '),
        trailing: AtlasCardButton(
          label: 'Olvidar',
          secondary: true,
          onPressed: () => _forget(entry),
        ),
      ),
    );
  }
}
