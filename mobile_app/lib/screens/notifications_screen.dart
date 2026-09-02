import 'package:flutter/material.dart';

import '../models/notification_item.dart';
import '../services/api_client.dart';
import '../theme/atlas_theme.dart';
import '../utils/format.dart';
import '../widgets/atlas_chrome.dart';

/// Avisos que genera el backend (recordatorios que vencen, rutinas que se
/// dispararon). Tocar uno lo marca como leído, igual que en el dashboard.
class NotificationsScreen extends StatefulWidget {
  final ApiClient apiClient;

  /// Avisa al shell cuántos quedan sin leer, para el globito de la pestaña.
  final ValueChanged<int> onUnreadChanged;

  const NotificationsScreen({super.key, required this.apiClient, required this.onUnreadChanged});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  List<NotificationItem> _items = [];
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
      final items = await widget.apiClient.listNotifications();
      if (!mounted) return;
      setState(() => _items = items);
      widget.onUnreadChanged(items.where((n) => !n.read).length);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) setState(() => _error = 'No se pudo conectar al servidor.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _markRead(NotificationItem item) async {
    if (item.read) return;
    try {
      await widget.apiClient.markNotificationRead(item.id);
      await _load();
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    return AtlasResourceList<NotificationItem>(
      items: _items,
      loading: _loading,
      error: _error,
      emptyMessage: 'Sin avisos.',
      onRefresh: _load,
      itemBuilder: (context, item) => InkWell(
        onTap: () => _markRead(item),
        borderRadius: BorderRadius.circular(AtlasRadius.card),
        child: AtlasCard(
          icon: item.read ? Icons.notifications_none : Icons.notifications_active_outlined,
          iconColor: item.read ? AtlasColors.textFaint : AtlasColors.accent,
          title: item.message,
          titleMaxLines: 3,
          subtitle: item.read ? formatShortDate(item.createdAt) : '${formatShortDate(item.createdAt)} · sin leer',
        ),
      ),
    );
  }
}
