import 'dart:io';
import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import 'api.dart';
import 'models.dart';

/// Archivos que generó ATLAS (ej. el Excel de una factura): se bajan del
/// backend una sola vez y se guardan, abren o comparten desde la tablet.
class GeneratedFiles {
  GeneratedFiles(this._api);

  final AtlasApi _api;
  final _cache = <String, Uint8List>{};

  Future<Uint8List> _bytes(GeneratedFile file) async => _cache[file.name] ??= await _api.downloadFile(file.name);

  Future<File> _local(GeneratedFile file) async {
    final dir = Directory('${(await getTemporaryDirectory()).path}/atlas-archivos');
    await dir.create(recursive: true);
    final target = File('${dir.path}/${file.name}');
    await target.writeAsBytes(await _bytes(file), flush: true);
    return target;
  }

  /// Diálogo del sistema para elegir dónde guardarlo (Descargas, Drive…).
  /// Devuelve false si el usuario canceló.
  Future<bool> save(GeneratedFile file) async {
    final uri = await FilePicker.saveFile(
      fileName: file.name,
      bytes: await _bytes(file),
      mimeType: file.mimeType,
      dialogTitle: 'Guardar ${file.name}',
    );
    return uri != null;
  }

  /// Lo abre con la app instalada para ese tipo (Excel, Hojas de cálculo…).
  Future<void> open(GeneratedFile file) async {
    final local = await _local(file);
    final result = await OpenFilex.open(local.path, type: file.mimeType);
    if (result.type == ResultType.noAppToOpen) {
      throw AtlasException('No hay ninguna app para abrir ${file.name}. Instala Excel o Hojas de cálculo de Google.');
    }
    if (result.type != ResultType.done) throw AtlasException(result.message);
  }

  Future<void> share(GeneratedFile file) async {
    final local = await _local(file);
    await SharePlus.instance.share(ShareParams(files: [XFile(local.path, mimeType: file.mimeType)], title: file.name));
  }
}
