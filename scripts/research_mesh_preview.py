#!/usr/bin/env python3
"""Loopback-only research viewer for a local I3S SLPK; does not redistribute it.

Usage: python scripts/research_mesh_preview.py /absolute/path/to/local.slpk
CesiumJS assets load from unpkg; no ion key, basemap or terrain service is used.
The source vertical datum is not corrected. This is a compatibility probe.
"""
import argparse
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile

PAGE = r'''<!doctype html><html><head><meta charset="utf-8">
<title>Local I3S compatibility research</title>
<script>window.CESIUM_BASE_URL='https://unpkg.com/cesium@1.146.0/Build/Cesium/';</script>
<script src="https://unpkg.com/cesium@1.146.0/Build/Cesium/Cesium.js"></script>
<link rel="stylesheet" href="https://unpkg.com/cesium@1.146.0/Build/Cesium/Widgets/widgets.css">
<style>html,body,#viewer{margin:0;width:100%;height:100%;overflow:hidden}#status{position:absolute;left:12px;top:12px;color:white;background:#111;padding:8px;font:12px monospace;max-width:80%;z-index:1}</style>
</head><body><div id="viewer"></div><pre id="status">Loading source package…</pre>
<script>
window.research={errors:[],loaded:false};
window.addEventListener('error',e=>{research.errors.push(e.message);document.querySelector('#status').textContent=e.message});
(async()=>{try{
const viewer=window.viewer=new Cesium.Viewer('viewer',{baseLayer:false,baseLayerPicker:false,geocoder:false,animation:false,timeline:false,homeButton:false,sceneModePicker:false,navigationHelpButton:false,fullscreenButton:false,terrainProvider:new Cesium.EllipsoidTerrainProvider(),skyBox:false,skyAtmosphere:false});
viewer.scene.globe.show=false;viewer.scene.backgroundColor=Cesium.Color.fromCssColorString('#20252b');
viewer.scene.renderError.addEventListener((s,e)=>{research.errors.push(String(e));document.querySelector('#status').textContent=String(e)});
const provider=window.provider=await Cesium.I3SDataProvider.fromUrl('/mesh/layers/0',{showFeatures:false,calculateNormals:true,cesium3dTilesetOptions:{maximumScreenSpaceError:8}});
viewer.scene.primitives.add(provider);research.loaded=true;research.layers=provider.layers.length;
const layerInfo=await fetch('/mesh/layers/0').then(r=>r.json());
const rootUrl=new URL(layerInfo.store.rootNode,location.origin+'/mesh/layers/0/');
const root=await fetch(rootUrl).then(r=>r.json());
const target=root.children?.[0]?.mbs??root.mbs;
viewer.camera.lookAt(Cesium.Cartesian3.fromDegrees(target[0],target[1],target[2]),new Cesium.HeadingPitchRange(Cesium.Math.toRadians(180),Cesium.Math.toRadians(-80),Math.max(1000,target[3]*1.9)));
viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
viewer.scene.light=new Cesium.DirectionalLight({direction:viewer.camera.directionWC,intensity:4});
document.querySelector('#status').textContent='I3S metadata loaded; source EGM96 heights uncorrected.';
}catch(e){research.errors.push(String(e));document.querySelector('#status').textContent=String(e);console.error(e)}})();
</script></body></html>'''

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package')
    parser.add_argument('--port', type=int, default=8183)
    args = parser.parse_args()
    archive = ZipFile(args.package)
    members = {name.replace('\\', '/'): name for name in archive.namelist()}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = unquote(urlsplit(self.path).path).strip('/')
            if not path:
                data, mime = PAGE.encode(), 'text/html; charset=utf-8'
            else:
                if not path.startswith('mesh/layers/0'):
                    self.send_error(404)
                    return
                path = path[len('mesh/layers/0'):].strip('/')
                if '..' in path.split('/'):
                    self.send_error(400)
                    return
                candidates = (["3dSceneLayer.json.gz"] if not path else
                    [path, path + '.json.gz', path + '.bin.gz', path + '.bin',
                     path + '/3dNodeIndexDocument.json.gz', path + '/sharedResource.json.gz'])
                found = next((p for p in candidates if p in members), None)
                if found is None:
                    self.send_error(404, path)
                    return
                data = archive.read(members[found])
                if found.endswith('.gz'):
                    data = gzip.decompress(data)
                mime = ('application/json' if '.json' in found else
                        'image/jpeg' if '/textures/' in found else 'application/octet-stream')
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    print(f'Local research only: http://127.0.0.1:{args.port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()

if __name__ == '__main__':
    main()
