import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:open_filex/open_filex.dart';

class FletInstaladorService extends FletService {
  FletInstaladorService({required super.control});

  @override
  void init() {
    super.init();
    control.addInvokeMethodListener(_invokeMethod);
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    debugPrint("FletInstaladorService.$name($args)");
    switch (name) {
      case "abrir":
        var resultado = await OpenFilex.open(args["caminho"]);
        return resultado.type.name;
      default:
        throw Exception("Unknown FletInstalador method: $name");
    }
  }

  @override
  void dispose() {
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }
}
