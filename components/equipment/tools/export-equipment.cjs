'use strict';
// Adapter to wow.export 0.2.19 internal interfaces. Supply a private app copy.
const fs = require('fs').promises;
const path = require('path');
async function run({ core, CASCRemote, db2 }) {
  const root = process.env.WXL_EQUIPMENT_EXPORT;
  const build = process.env.WXL_EQUIPMENT_BUILD;
  if (!root || !/^[a-f0-9]{32}$/.test(build || '')) throw Error('Explicit export directory and BuildConfig required');
  await fs.mkdir(root, {recursive:true});
  const status = async value => fs.writeFile(path.join(root,'status.json'),JSON.stringify(value,null,2));
  try {
    await status({state:'initializing'});
    const source = new CASCRemote('us'); await source.init();
    const index=source.builds.findIndex(b=>b.Product==='wow' && b.BuildConfig===build);
    if(index<0) throw Error('Pinned BuildConfig unavailable; no substitution');
    await fs.writeFile(path.join(root,'build.json'),JSON.stringify(source.builds[index],null,2));
    await status({state:'loading-cached-casc'}); await source.load(index); core.view.casc=source;
    const tables=['ItemModifiedAppearance','ItemAppearance','ItemDisplayInfo','ItemDisplayInfoMaterialRes','ItemDisplayInfoModelMatRes','TextureFileData','ModelFileData'];
    for(const name of (process.env.WXL_EQUIPMENT_FILES==='1' ? [] : tables)){
      await status({state:'table',name});
      const rows=[...(await db2[name].getAllRows()).entries()].map(([ID,row])=>({ID,...row}));
      await fs.writeFile(path.join(root,name+'.json'),JSON.stringify(rows));
    }
    const requests=JSON.parse(await fs.readFile(path.join(root,'requests.json'),'utf8').catch(()=> '[]'));
    if(requests.length>32) throw Error('Pilot limited to 32 explicit FileDataIDs');
    for(const id of requests){
      if(!Number.isSafeInteger(id)||id<=0)throw Error('Invalid FileDataID');
      await status({state:'file',id});
      await (await source.getFile(id)).writeToFile(path.join(root,id+'.bin'));
    }
    await status({state:'complete',build,files:requests.length});
  } catch(error){await status({state:'failed',error:String(error)});}
}
module.exports={run};
