import logging

import httpx

logger = logging.getLogger("menu")

OFF_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
TIMEOUT = 4.0
MAX_RESULTS = 5


def rechercher_ingredient(terme: str) -> list[dict]:
    """
    Interroge l'API Open Food Facts et retourne jusqu'à 5 suggestions
    avec les macros pour 100g.
    Retourne une liste vide en cas d'erreur ou d'absence de résultats.
    """
    terme = terme.strip()
    if not terme or len(terme) < 2:
        return []

    try:
        resp = httpx.get(
            OFF_SEARCH_URL,
            params={
                "search_terms": terme,
                "search_simple": 1,
                "action": "process",
                "json": 1,
                "page_size": 20,
                "fields": "code,product_name,nutriments",
            },
            timeout=TIMEOUT,
            headers={"User-Agent": "MenuFamilialApp/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("Open Food Facts indisponible pour '%s' : %s", terme, exc)
        return []

    results = []
    for product in data.get("products", []):
        name = (product.get("product_name") or "").strip()
        if not name:
            continue
        nutriments = product.get("nutriments") or {}
        calories = nutriments.get("energy-kcal_100g") or nutriments.get("energy_100g")
        if calories and "energy-kcal_100g" not in nutriments:
            # Convertir kJ → kcal si nécessaire
            calories = round(calories / 4.184, 1)
        results.append({
            "id": product.get("code", ""),
            "name": name,
            "calories": round(float(calories), 1) if calories else None,
            "proteins": round(float(nutriments.get("proteins_100g", 0) or 0), 1),
            "carbs": round(float(nutriments.get("carbohydrates_100g", 0) or 0), 1),
            "fats": round(float(nutriments.get("fat_100g", 0) or 0), 1),
        })
        if len(results) >= MAX_RESULTS:
            break

    return results
