from app.repositories.seed_data import load_seed_pois


if __name__ == "__main__":
    pois = load_seed_pois()
    print(f"seed_poi_count={len(pois)}")
    print(f"first_poi={pois[0].id} {pois[0].name}")
