from filever import discover, set_version
from filever.disk import list_on_disk
from filever import discover, find_on_disk

pv = discover("L:/projects/82116_Hyundai_HOW_OOH/_04_shows/HOW/HOW_030/light/HOW_030_LIGHT/scenes/HOW_030_LIGHT_v003.max")

versions = find_on_disk(pv)

for dv in versions:
    print(f"{dv} - {dv.path}")
    print(vars(dv))