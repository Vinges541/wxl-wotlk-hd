# Attribution and excluded assets

- `src/wxl_equipment/assets.py` adapts the StormLib ctypes reader pattern from
  [wxl-modern-races](https://github.com/Vinges541/wxl-modern-races), source profile
  `f8f22e7`, GPL-3.0-or-later. Modified for explicit archive inputs, provenance,
  cached handles and bounded decoding.
- The optional PyTorch SRVGG architecture follows
  [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN), revision
  `a4abfb2979a7bbff3f69f58f58ae324608821e27`, BSD-3-Clause, Xintao Wang (2021).
  Full notice: [models/Real-ESRGAN-LICENSE](models/Real-ESRGAN-LICENSE).
  Official release weights are fetched separately; source and converted hashes are
  recorded in model locks. No weights are redistributed. RealESRNet is released
  through this upstream repository; no separate weight license was found.
- [realesrgan-mlx](https://github.com/xocialize/realesrgan-mlx), revision
  `52c0fc1044277900b995308095a1f3cc484a3581`, is an external BSD-3-Clause dependency.
  Its README and package metadata declare BSD-3-Clause inherited from upstream;
  the inspected revision has no standalone LICENSE file. No port source is vendored.
  Its converted model cards identify BSD-3-Clause weight licensing. The project
  loads only explicitly supplied local weight directories.
- [wow.export](https://github.com/Kruithne/wow.export) 0.2.19, MIT, Kruithne and
  Marlamin: external exporter. The adapter calls its bundled internal interfaces;
  its application code is not redistributed by this project.
- [StormLib](https://github.com/ladislav-zezula/StormLib) 9.30 is supplied/built
  separately from the pinned wxl-core dependency. Its source carries its license.
  The independent MPQ verifier implements the legacy hash/table and sector format
  described by its `StormLib.h` and `SBaseCommon.cpp`; the native writer/readback
  calls the externally supplied library. Its MIT notice is retained in
  [models/StormLib-LICENSE](models/StormLib-LICENSE). No StormLib binary is distributed.
- MLX/MLX Metal, PyTorch, Pillow, NumPy and optional package dependencies carry
  their own licenses in their distributions; they are installed separately.

Game textures, models, databases, archives, executables, trademarks and generated
outputs are excluded and remain subject to their owners' rights. This source
license grants no rights to redistribute game content.
