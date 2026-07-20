from filever import all_versions, discover

pv = discover("L:/projects/82116_Hyundai_HOW_OOH/_04_shows/HOW/HOW_030/light/HOW_030_LIGHT/scenes/HOW_030_LIGHT_v003.max")

versions = all_versions(pv)

for vf in versions:
    print(f"{vf} - {vf.path}")
    print(vars(vf))
