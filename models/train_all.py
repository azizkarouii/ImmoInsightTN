"""Ré-entraînement planifié des modèles de prix, puis recalcul des opportunités.

python -m models.train_all
"""
import sys
import traceback


def run():
    from models.m1_avm_vente.train import run as train_m1
    from models.m2_loyer_classique.train import run as train_m2
    from models.m3_pricing_estival.train import run as train_m3
    from models.opportunites import run as run_opportunites

    echecs = []
    for nom, etape in [("M1 vente", train_m1), ("M2 loyer", train_m2), ("M3 estival", train_m3)]:
        try:
            etape()
        except Exception:
            # Un modèle en échec ne doit pas empêcher les autres : l'ancien reste en place
            traceback.print_exc()
            echecs.append(nom)

    run_opportunites()
    if echecs:
        print(f"[TRAIN] Echecs : {', '.join(echecs)}")
        sys.exit(1)
    print("[TRAIN] Termine : M1, M2, M3 re-entraines")


if __name__ == "__main__":
    run()
