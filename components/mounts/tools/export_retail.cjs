// Source adapter for the explicitly supplied wow.export 0.2.19 bundle.
// Evaluates its lazy modules without starting the UI or modifying the application.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const hash = data => crypto.createHash('sha256').update(data).digest('hex');
function physical(value) {
  const full = path.resolve(value);
  for (let p = full;; p = path.dirname(p)) {
    if (fs.existsSync(p) && fs.lstatSync(p).isSymbolicLink()) throw Error('Supply physical paths; nested symlinks are unsupported');
    if (p === path.dirname(p)) break;
  }
  return full;
}
function overlaps(a, b) {
  return a === b || a.startsWith(b + path.sep) || b.startsWith(a + path.sep);
}

async function main() {
  const [appArg, profileArg, requestArg, outArg] = process.argv.slice(2);
  if (!outArg) throw Error('Usage: node tools/export_retail.cjs app.nw private-profile request.json fresh-output');
  const app = physical(appArg), profile = physical(profileArg);
  const out = physical(outArg), request = JSON.parse(fs.readFileSync(physical(requestArg)));
  if (fs.existsSync(out)) throw Error('Output must be fresh');
  if (!fs.statSync(profile).isDirectory() || overlaps(app, profile) || overlaps(app, out) || overlaps(profile, out))
    throw Error('Application, private profile and fresh output must be separate');
  const build = request.build;
  if (!build || build.Product !== 'wow' || build.BuildConfig !== 'c9fa1a64b0170829cc5c5c98c71025c3'
      || build.CDNConfig !== '3aa83893a3ce9b722a5f51328ad9a552')
    throw Error('Explicit pinned build and CDN metadata required');
  for (const key of ['models', 'textures', 'probes']) {
    if (request[key] !== undefined && (!Array.isArray(request[key]) || request[key].some(id => !Number.isSafeInteger(id) || id <= 0)))
      throw Error('Invalid ' + key + ' FileDataID list');
  }
  const allowedTables = ['CreatureDisplayInfo', 'CreatureModelData', 'CreatureDisplayInfoGeosetData', 'Mount', 'MountXDisplay'];
  if (request.tables !== undefined && (!Array.isArray(request.tables) || request.tables.some(n => !allowedTables.includes(n))))
    throw Error('Unexpected table request');
  const manifest = JSON.parse(fs.readFileSync(path.join(app, 'package.json')));
  if (manifest.version !== '0.2.19') throw Error('Unsupported wow.export version');
  const bundle = fs.readFileSync(path.join(app, 'src/app.js'), 'utf8');
  if (hash(bundle) !== 'bcaf033793929060d1040c18619b6bbcfa901e4e1c25ae406cfa63f3069f0dd5')
    throw Error('Pinned wow.export bundle required');
  const begin = bundle.indexOf('var __defProp = Object.defineProperty;');
  const end = bundle.lastIndexOf('// src/app.js\n');
  if (begin < 0 || end <= begin) throw Error('Unsupported lazy-module bundle');
  fs.mkdirSync(out);
  const nw = {__dirname: app, App: {dataPath: profile, manifest, argv: []}};
  const api = new Function('require', 'nw', 'BUILD_RELEASE',
    bundle.slice(begin, end) + '\nreturn {core:require_core(), generics:require_generics(),'+
    'CASCRemote:require_casc_source_remote(), constants:require_constants(),'+
    'tact:require_tact_keys(), db2:require_db2(), M2Exporter:require_M2Exporter()};'
  )(require, nw, true);
  api.core.view = api.core.makeNewView();
  api.core.view.$watch = () => {};
  api.core.showLoadingScreen = () => {};
  api.core.hideLoadingScreen = () => {};
  api.core.progressLoadingScreen = async text => console.log(text);
  api.core.setToast = () => {};
  api.core.view.config = await api.generics.readJSON(path.join(app, 'src/default_config.jsonc'), true);
  Object.assign(api.core.view.config, {
    exportDirectory: out, enableSharedChildren: true, enableSharedTextures: true,
    modelsExportTextures: true, modelsExportSkin: true, modelsExportSkel: true,
    modelsExportBone: true, modelsExportAnim: true, overwriteFiles: false,
    removePathSpaces: false, pathFormat: 'posix'
  });
  await api.tact.load();
  const source = new api.CASCRemote('us');
  source.locale = api.core.view.config.cascLocale || 2; // enUS, no Vue watcher in headless mode.
  // Use saved exact-build metadata; never substitute the current CDN default.
  source.host = 'http://us.patch.battle.net:1119/';
  source.builds = [build];
  const state = {state: 'loading', build, models: [], files: [], tables: [],
    bundleSha256: crypto.createHash('sha256').update(bundle).digest('hex')};
  function save() {
    fs.writeFileSync(path.join(out, 'status.json.tmp'), JSON.stringify(state, null, 2));
    fs.renameSync(path.join(out, 'status.json.tmp'), path.join(out, 'status.json'));
  }
  save();
  try {
    await source.load(0);
    api.core.view.casc = source;
    if (request.probes?.length) fs.mkdirSync(path.join(out, 'probes'));
    for (const id of [...new Set(request.probes || [])]) {
      if (!Number.isSafeInteger(id) || id <= 0) throw Error('Invalid probe FileDataID');
      await (await source.getFile(id)).writeToFile(path.join(out, 'probes', id + '.m2'));
    }
    for (const name of request.tables || []) {
      const rows = [...(await api.db2[name].getAllRows()).entries()].map(([ID, row]) => ({ID, ...row}));
      fs.writeFileSync(path.join(out, name + '.json'), JSON.stringify(rows));
      state.tables.push({name, rows: rows.length, sha256: hash(fs.readFileSync(path.join(out, name + '.json')))}); save(); console.log(name, rows.length);
    }
    for (const id of [...new Set(request.models || [])]) {
      if (!Number.isSafeInteger(id) || id <= 0) throw Error('Invalid model FileDataID');
      const record = {fileDataId: id, state: 'exporting'};
      state.models.push(record); state.current = id; save();
      try {
        const destination = path.join(out, id + '.m2');
        const files = [];
        await new api.M2Exporter(await source.getFile(id), [], id)
          .exportRaw(destination, {isCancelled: () => false}, files);
        for (const entry of files) {
          const p = physical(entry.file);
          if (!p.startsWith(out + path.sep)) throw Error('Exported dependency escaped output');
          entry.size = fs.statSync(p).size; entry.sha256 = hash(fs.readFileSync(p));
        }
        fs.writeFileSync(path.join(out, id + '.files.manifest.json'), JSON.stringify({files}, null, 2));
        record.state = 'complete';
      } catch (error) {
        record.state = 'failed'; record.error = error.stack || String(error);
      }
      console.log('model', id, record.state); save();
    }
    fs.mkdirSync(path.join(out, 'textures'));
    for (const id of [...new Set(request.textures || [])].filter(Boolean)) {
      if (!Number.isSafeInteger(id) || id <= 0) throw Error('Invalid texture FileDataID');
      const record = {fileDataId: id}; state.files.push(record);
      try {
        await (await source.getFile(id)).writeToFile(path.join(out, 'textures', id + '.blp'));
        record.sha256 = hash(fs.readFileSync(path.join(out, 'textures', id + '.blp')));
        record.state = 'complete';
      } catch (error) { record.state = 'failed'; record.error = error.stack || String(error); }
      save();
    }
    state.state = [...state.models, ...state.files].some(r => r.state === 'failed') ? 'partial' : 'complete';
    delete state.current; save();
    fs.writeFileSync(path.join(out, 'build.json'), JSON.stringify(build, null, 2));
    console.log(state.state);
  } catch (error) { state.state = 'failed'; state.error = error.stack || String(error); save(); throw error; }
}
main().then(() => process.exit(0)).catch(error => {console.error(error); process.exit(1);});
