"""Reproducible CPU algorithm profile; does not claim Maya/GPU timings."""
import json
import platform
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'AbnormalMaya'/'scripts'))
from abnormal_maya import core,display,selection


def run():
    results=[]
    for width in (40,100):
        points=[(x,y,0) for y in range(width) for x in range(width)]
        faces=[[y*width+x,y*width+x+1,(y+1)*width+x+1,(y+1)*width+x]
               for y in range(width-1) for x in range(width-1)]
        row={'vertices':len(points),'corners':len(faces)*4}
        start=time.perf_counter()
        mesh=core.Mesh(points,faces,[(0,0,1)]*(len(faces)*4),[(0,0,1)]*len(faces))
        row['mesh_build_seconds']=time.perf_counter()-start
        start=time.perf_counter()
        payload=display.batches(mesh,wedges=True)
        row['overlay_geometry_seconds']=time.perf_counter()-start
        row['draw_batches']=len(payload)
        start=time.perf_counter()
        core.edit(mesh,set(range(len(mesh.normals))),'smooth',iterations=5)
        row['five_smooth_iterations_seconds']=time.perf_counter()-start
        start=time.perf_counter()
        topology=selection.Topology(mesh);path=topology.path(0,len(points)-1)
        row['topology_and_path_seconds']=time.perf_counter()-start
        row['path_vertices']=len(path)
        results.append(row)
    result={'python':platform.python_version(),'kind':'CPU algorithms only; not Maya API or GPU', 'meshes':results}
    print(json.dumps(result,indent=2))
    return result


if __name__=='__main__': run()
