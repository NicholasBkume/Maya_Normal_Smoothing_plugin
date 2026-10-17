"""Validated, versioned optionVar preferences; never stores scene state."""
import json
import math

DEFAULTS=dict(individual=False,space='Object',axis='Y',angle=5.0,strength=.25,
              iterations=5,tolerance=0.0,normal_size=.4,overlay_selected_only=False,
              overlay_scale_selected=True,overlay_weights=False,overlay_wedges=False,
              overlay_xray=False,overlay_point_size=4.0,selection_mode='Click',
              selection_radius=25.0,shortcuts_enabled=True,overlay_brightness=1.0,
              overlay_wedge_scale=.18,overlay_wireframe=False,ui_scale=1.0)
ENUMS=dict(space=('Object','World','View'),axis=('X','Y','Z'),selection_mode=('Click','Box','Circle','Lasso'))
RANGES=dict(angle=(-360,360),strength=(0,1),iterations=(1,100),tolerance=(0,1e6),
            normal_size=(.001,1e4),overlay_point_size=(1,20),selection_radius=(1,300),overlay_brightness=(.1,3),
            overlay_wedge_scale=(.01,.5),ui_scale=(.5,2))
KEY='abnormalMayaPreferencesV1'


def validate(values):
    result=dict(DEFAULTS)
    if not isinstance(values,dict): raise ValueError('Preferences must be an object')
    for key,value in values.items():
        if key not in DEFAULTS: continue
        if key in ENUMS:
            if value not in ENUMS[key]: raise ValueError('Invalid preference: '+key)
        elif isinstance(DEFAULTS[key],bool):
            if not isinstance(value,bool): raise ValueError('Expected boolean preference: '+key)
        else:
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                raise ValueError('Expected finite numeric preference: '+key)
            low,high=RANGES[key]
            if not low<=value<=high: raise ValueError('Preference outside range: '+key)
            if isinstance(DEFAULTS[key],int): value=int(value)
        result[key]=value
    return result


def load():
    from maya import cmds
    if not cmds.optionVar(exists=KEY): return dict(DEFAULTS)
    try: return validate(json.loads(cmds.optionVar(query=KEY)))
    except (ValueError,TypeError):
        cmds.warning('Abnormal preferences are invalid; using defaults')
        return dict(DEFAULTS)


def save(values):
    from maya import cmds
    cmds.optionVar(stringValue=(KEY,json.dumps(validate(values),sort_keys=True)))
