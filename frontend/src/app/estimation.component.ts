import { API_BASE } from './api.config';
import { Component, OnInit } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { IconComponent } from './icon.component';

type Mode = 'vente' | 'location' | 'estival' | 'roi';

interface Resultat {
  valeur: number;
  bas?: number;
  haut?: number;
  unite: string;
  erreur?: number | null;
  zone?: string | null;
  zoneDemandee?: string;
  details: { libelle: string; valeur: string }[];
}

const CLE_STOCKAGE = 'immoinsight-estimation';
const nf = (v: number, d = 0) => Number(v).toLocaleString('fr-FR', { maximumFractionDigits: d });

@Component({
  selector: 'app-estimation',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  template: `
    <div class="card">
      <div class="section-head">
        <div>
          <p class="eyebrow">Estimer un bien</p>
          <h2>Combien vaut-il ? Combien peut-il rapporter ?</h2>
          <p class="section-copy">Estimations issues des modèles entraînés sur les annonces de la plateforme, avec leur marge d'erreur réelle.</p>
        </div>
      </div>

      <div class="mode-tabs" role="tablist" aria-label="Type d'estimation">
        <button *ngFor="let m of modes" role="tab" [attr.aria-selected]="mode === m.id" [class.active]="mode === m.id" (click)="changerMode(m.id)">
          <app-icon class="mode-icone" [name]="m.icone"></app-icon>
          <span>{{ m.libelle }}</span>
          <small>{{ m.aide }}</small>
        </button>
      </div>

      <div class="estim-grid">
        <!-- ===================== Formulaires ===================== -->
        <form class="estim-form" (ngSubmit)="estimer()" novalidate>
          <ng-container [ngSwitch]="mode">

            <ng-container *ngSwitchCase="'vente'">
              <div class="champ">
                <label for="v-zone">Ville ou quartier</label>
                <input id="v-zone" name="vzone" list="zones-vente" [(ngModel)]="vente.zone" placeholder="ex. La Marsa, Ennasr, Sousse" autocomplete="off" />
                <datalist id="zones-vente"><option *ngFor="let z of zones.vente" [value]="z"></option></datalist>
              </div>
              <div class="champ">
                <label for="v-surface">Surface habitable <span class="requis">*</span></label>
                <div class="avec-unite">
                  <input id="v-surface" name="vsurface" type="number" min="1" [(ngModel)]="vente.surface" placeholder="ex. 120" [class.invalide]="erreurs['surface']" />
                  <span>m²</span>
                </div>
                <p class="champ-erreur" *ngIf="erreurs['surface']">{{ erreurs['surface'] }}</p>
              </div>
              <div class="champ">
                <label>Type de bien</label>
                <div class="choix">
                  <button type="button" *ngFor="let t of typesVente" [class.actif]="vente.type_bien === t.id" (click)="vente.type_bien = t.id">{{ t.libelle }}</button>
                </div>
              </div>
              <div class="champ">
                <label for="v-ch">Chambres</label>
                <select id="v-ch" name="vch" [(ngModel)]="vente.chambres">
                  <option [ngValue]="null">Non précisé</option>
                  <option *ngFor="let c of chambres" [ngValue]="c.valeur">{{ c.libelle }}</option>
                </select>
              </div>
              <div class="champ">
                <label>Équipements</label>
                <div class="choix">
                  <button type="button" [class.actif]="vente.parking" (click)="vente.parking = !vente.parking">Parking</button>
                  <button type="button" [class.actif]="vente.ascenseur" (click)="vente.ascenseur = !vente.ascenseur">Ascenseur</button>
                  <button type="button" [class.actif]="vente.piscine" (click)="vente.piscine = !vente.piscine">Piscine</button>
                </div>
              </div>
            </ng-container>

            <ng-container *ngSwitchCase="'location'">
              <div class="champ">
                <label for="l-zone">Ville ou quartier</label>
                <input id="l-zone" name="lzone" list="zones-location" [(ngModel)]="location.zone" placeholder="ex. La Marsa, Ennasr, Sousse" autocomplete="off" />
                <datalist id="zones-location"><option *ngFor="let z of zones.location" [value]="z"></option></datalist>
              </div>
              <div class="champ">
                <label for="l-surface">Surface habitable</label>
                <div class="avec-unite">
                  <input id="l-surface" name="lsurface" type="number" min="1" [(ngModel)]="location.surface" placeholder="ex. 90" [class.invalide]="erreurs['surface']" />
                  <span>m²</span>
                </div>
                <p class="champ-erreur" *ngIf="erreurs['surface']">{{ erreurs['surface'] }}</p>
              </div>
              <div class="champ">
                <label>Type de bien</label>
                <div class="choix">
                  <button type="button" [class.actif]="location.type_bien === 'appartement'" (click)="location.type_bien = 'appartement'">Appartement</button>
                  <button type="button" [class.actif]="location.type_bien === 'villa'" (click)="location.type_bien = 'villa'">Villa / étage de villa</button>
                </div>
              </div>
              <div class="champ-ligne">
                <div class="champ">
                  <label for="l-ch">Chambres</label>
                  <select id="l-ch" name="lch" [(ngModel)]="location.chambres">
                    <option [ngValue]="null">Non précisé</option>
                    <option *ngFor="let c of chambres" [ngValue]="c.valeur">{{ c.libelle }}</option>
                  </select>
                </div>
                <div class="champ">
                  <label for="l-sdb">Salles de bain</label>
                  <select id="l-sdb" name="lsdb" [(ngModel)]="location.sdb">
                    <option [ngValue]="null">Non précisé</option>
                    <option [ngValue]="1">1</option><option [ngValue]="2">2</option><option [ngValue]="3">3 et +</option>
                  </select>
                </div>
              </div>
              <div class="champ">
                <label>Ameublement</label>
                <div class="choix">
                  <button type="button" [class.actif]="location.meuble === null" (click)="location.meuble = null">Non précisé</button>
                  <button type="button" [class.actif]="location.meuble === true" (click)="location.meuble = true">Meublé</button>
                  <button type="button" [class.actif]="location.meuble === false" (click)="location.meuble = false">Vide</button>
                </div>
              </div>
            </ng-container>

            <ng-container *ngSwitchCase="'estival'">
              <div class="champ">
                <label for="e-ville">Ville balnéaire <span class="requis">*</span></label>
                <select id="e-ville" name="eville" [(ngModel)]="estival.ville" [class.invalide]="erreurs['ville']">
                  <option value="">— Choisir —</option>
                  <option *ngFor="let v of villesEstivales" [value]="v">{{ v }}</option>
                </select>
                <p class="champ-erreur" *ngIf="erreurs['ville']">{{ erreurs['ville'] }}</p>
              </div>
              <div class="champ">
                <label>Type de logement</label>
                <div class="choix">
                  <button type="button" [class.actif]="!estival.categorie" (click)="estival.categorie = null">Non précisé</button>
                  <button type="button" [class.actif]="estival.categorie === 'appartement'" (click)="estival.categorie = 'appartement'">Appartement</button>
                  <button type="button" [class.actif]="estival.categorie === 'maison_vacances'" (click)="estival.categorie = 'maison_vacances'">Maison</button>
                  <button type="button" [class.actif]="estival.categorie === 'villa'" (click)="estival.categorie = 'villa'">Villa</button>
                </div>
              </div>
              <div class="champ-ligne">
                <div class="champ">
                  <label for="e-ch">Chambres</label>
                  <select id="e-ch" name="ech" [(ngModel)]="estival.chambres">
                    <option [ngValue]="null">Non précisé</option>
                    <option *ngFor="let c of chambres" [ngValue]="c.valeur">{{ c.libelle }}</option>
                  </select>
                </div>
                <div class="champ">
                  <label for="e-lits">Couchages</label>
                  <input id="e-lits" name="elits" type="number" min="1" max="40" [(ngModel)]="estival.lits" placeholder="ex. 4" />
                </div>
              </div>
              <div class="champ">
                <label for="e-surface">Surface</label>
                <div class="avec-unite">
                  <input id="e-surface" name="esurface" type="number" min="1" [(ngModel)]="estival.surface" placeholder="ex. 100" />
                  <span>m²</span>
                </div>
              </div>
              <div class="champ">
                <label>Emplacement</label>
                <div class="choix">
                  <button type="button" [class.actif]="estival.front_de_mer === true" (click)="estival.front_de_mer = estival.front_de_mer === true ? null : true">Front de mer</button>
                </div>
              </div>
            </ng-container>

            <ng-container *ngSwitchCase="'roi'">
              <div class="champ">
                <label for="r-prix">Prix d'achat <span class="requis">*</span></label>
                <div class="avec-unite">
                  <input id="r-prix" name="rprix" type="number" min="1" [(ngModel)]="roi.prix" placeholder="ex. 300000" [class.invalide]="erreurs['prix']" />
                  <span>TND</span>
                </div>
                <p class="champ-erreur" *ngIf="erreurs['prix']">{{ erreurs['prix'] }}</p>
              </div>
              <div class="champ">
                <label for="r-loyer">Loyer mensuel (location à l'année)</label>
                <div class="avec-unite">
                  <input id="r-loyer" name="rloyer" type="number" min="0" [(ngModel)]="roi.loyer" placeholder="ex. 1500" [class.invalide]="erreurs['revenus']" />
                  <span>TND/mois</span>
                </div>
              </div>
              <div class="champ">
                <label for="r-nuit">Prix par nuit (location estivale)</label>
                <div class="avec-unite">
                  <input id="r-nuit" name="rnuit" type="number" min="0" [(ngModel)]="roi.nuit" placeholder="ex. 250" [class.invalide]="erreurs['revenus']" />
                  <span>TND/nuit</span>
                </div>
                <p class="champ-erreur" *ngIf="erreurs['revenus']">{{ erreurs['revenus'] }}</p>
              </div>
              <div class="champ" *ngIf="roi.nuit">
                <label for="r-nuits">Nuits louées par an : <strong>{{ roi.nuits }}</strong></label>
                <input id="r-nuits" name="rnuits" type="range" min="10" max="180" step="5" [(ngModel)]="roi.nuits" />
                <p class="champ-aide">En Tunisie, la saison couvre surtout juin à septembre (≈ 60 à 100 nuits).</p>
              </div>
            </ng-container>
          </ng-container>

          <div class="estim-actions">
            <button type="submit" class="btn btn-accent" [disabled]="chargement">
              <span *ngIf="chargement" class="spinner spinner-sm"></span>
              {{ mode === 'roi' ? 'Calculer la rentabilité' : 'Estimer' }}
            </button>
            <button type="button" class="btn-lien" (click)="reinitialiser()">Effacer</button>
          </div>
        </form>

        <!-- ===================== Résultat ===================== -->
        <section class="estim-result" aria-live="polite">
          <div class="result-vide" *ngIf="!chargement && !erreur && (mode === 'roi' ? !roiResultat : !resultat[mode])">
            <app-icon class="result-vide-icone" [name]="modeCourant().icone"></app-icon>
            <p>{{ modeCourant().vide }}</p>
          </div>

          <div class="result-chargement" *ngIf="chargement"><div class="spinner"></div>Calcul en cours…</div>
          <div class="result-erreur" *ngIf="erreur && !chargement" role="alert"><app-icon name="alert"></app-icon>{{ erreur }}</div>

          <ng-container *ngIf="mode !== 'roi' && resultat[mode] as r">
            <ng-container *ngIf="!chargement && !erreur">
              <span class="result-label">{{ modeCourant().resultat }}</span>
              <div class="result-valeur">{{ format(r.valeur) }} <span>{{ r.unite }}</span></div>

              <div class="fourchette" *ngIf="r.bas && r.haut">
                <div class="fourchette-barre">
                  <span class="fourchette-point" [style.left.%]="position(r)"></span>
                </div>
                <div class="fourchette-bornes">
                  <span>{{ format(r.bas) }}</span>
                  <span class="muted">fourchette probable (80 %)</span>
                  <span>{{ format(r.haut) }}</span>
                </div>
              </div>

              <p class="result-note" *ngIf="r.erreur">Erreur typique du modèle : ±{{ r.erreur | number:'1.0-0' }} % (médiane mesurée sur des annonces réelles).</p>
              <p class="result-zone ok" *ngIf="r.zone"><app-icon name="pin"></app-icon>Zone prise en compte : {{ r.zone }}</p>
              <p class="result-zone attention" *ngIf="!r.zone && r.zoneDemandee"><app-icon name="alert"></app-icon>« {{ r.zoneDemandee }} » n'apparaît pas dans les données : estimation sans effet de la localisation.</p>

              <dl class="result-details" *ngIf="r.details.length">
                <div *ngFor="let d of r.details"><dt>{{ d.libelle }}</dt><dd>{{ d.valeur }}</dd></div>
              </dl>

              <button type="button" class="btn btn-secondaire" (click)="versRentabilite()"><app-icon name="trending-up"></app-icon>{{ texteVersRoi() }}</button>
            </ng-container>
          </ng-container>

          <ng-container *ngIf="mode === 'roi' && roiResultat as r">
            <ng-container *ngIf="!chargement && !erreur">
              <span class="result-label">Rendement net annuel</span>
              <div class="result-valeur">{{ r.rendement_net_pct | number:'1.1-1' }} <span>%</span>
                <span class="badge" [ngClass]="classeRoi(r.label_roi)">{{ r.label_roi }}</span>
              </div>
              <div class="score">
                <div class="score-barre"><span [style.width.%]="r.score_roi" [ngClass]="classeRoi(r.label_roi)"></span></div>
                <span class="muted">Score {{ r.score_roi }}/100</span>
              </div>
              <dl class="result-details">
                <div><dt>Rendement brut</dt><dd>{{ r.rendement_brut_pct | number:'1.1-1' }} %</dd></div>
                <div><dt>Retour sur investissement</dt><dd>{{ r.temps_retour_annees ? (r.temps_retour_annees | number:'1.0-1') + ' ans' : '—' }}</dd></div>
                <div><dt>Coût total d'acquisition</dt><dd>{{ r.cout_total_acquisition | number:'1.0-0' }} TND</dd></div>
                <div><dt>Revenu annuel</dt><dd>{{ r.revenu_annuel_total | number:'1.0-0' }} TND</dd></div>
                <div *ngIf="r.revenu_annuel_classique"><dt>dont location à l'année</dt><dd>{{ r.revenu_annuel_classique | number:'1.0-0' }} TND</dd></div>
                <div *ngIf="r.revenu_annuel_estival"><dt>dont location estivale</dt><dd>{{ r.revenu_annuel_estival | number:'1.0-0' }} TND</dd></div>
              </dl>
              <p class="result-note">Hypothèses : frais d'acquisition 5 %, charges et taxes déduites du rendement net. Rendement médian observé (appartements) : {{ rendementMedian ? (rendementMedian | number:'1.1-1') + ' %' : '—' }} brut.</p>
            </ng-container>
          </ng-container>
        </section>
      </div>
    </div>

    <div class="card" style="margin-top:20px" *ngIf="mode === 'roi' || mode === 'location'">
      <div class="section-head">
        <div>
          <p class="eyebrow">Repères de marché</p>
          <h2>Rendement locatif brut par ville</h2>
          <p class="section-copy">Appartements : loyer médian × 12 / prix de vente médian, villes avec au moins 5 annonces de chaque.</p>
        </div>
      </div>
      <div class="table-wrap" *ngIf="rendements.length; else rendVide">
        <table>
          <thead><tr><th>Ville</th><th>Rendement brut</th><th>Prix médian</th><th>Loyer médian</th><th></th></tr></thead>
          <tbody>
            <tr *ngFor="let z of rendements">
              <td><strong>{{ z.ville }}</strong><div class="muted small">{{ z.n_vente }} ventes · {{ z.n_location }} locations</div></td>
              <td><span class="badge badge-info">{{ z.rendement_brut_pct | number:'1.1-1' }} %</span></td>
              <td>{{ z.prix_median | number:'1.0-0' }} TND</td>
              <td>{{ z.loyer_median | number:'1.0-0' }} TND/mois</td>
              <td><button type="button" class="btn-lien" (click)="simulerZone(z)">Simuler</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <ng-template #rendVide><p class="muted">Classement indisponible pour le moment.</p></ng-template>
    </div>
  `,
  styles: []
})
export class EstimationComponent implements OnInit {
  modes: { id: Mode; icone: string; libelle: string; aide: string; resultat: string; vide: string }[] = [
    { id: 'vente', icone: 'tag', libelle: 'Prix de vente', aide: 'Combien vaut ce bien ?', resultat: 'Prix de vente estimé',
      vide: 'Indiquez au minimum la surface, puis lancez l\'estimation.' },
    { id: 'location', icone: 'house', libelle: 'Loyer mensuel', aide: 'Location à l\'année', resultat: 'Loyer mensuel estimé',
      vide: 'Précisez la ville et la surface pour une estimation plus fiable.' },
    { id: 'estival', icone: 'waves', libelle: 'Location estivale', aide: 'Prix par nuit', resultat: 'Prix par nuit estimé',
      vide: 'Choisissez une ville balnéaire ; ajoutez le type et les chambres pour affiner.' },
    { id: 'roi', icone: 'trending-up', libelle: 'Rentabilité', aide: 'Rendement d\'un achat', resultat: '',
      vide: 'Saisissez un prix d\'achat et un loyer et/ou un prix par nuit. Astuce : estimez-les dans les autres onglets.' },
  ];
  typesVente = [{ id: 'appartement', libelle: 'Appartement' }, { id: 'villa', libelle: 'Villa / maison' }, { id: 'terrain', libelle: 'Terrain' }];
  chambres = [
    { valeur: 0, libelle: 'Studio (S+0)' }, { valeur: 1, libelle: 'S+1' }, { valeur: 2, libelle: 'S+2' },
    { valeur: 3, libelle: 'S+3' }, { valeur: 4, libelle: 'S+4' }, { valeur: 5, libelle: 'S+5 et +' },
  ];

  mode: Mode = 'vente';
  vente = { zone: '', surface: null as number | null, type_bien: 'appartement', chambres: null as number | null, parking: false, ascenseur: false, piscine: false };
  location = { zone: '', surface: null as number | null, type_bien: 'appartement', chambres: null as number | null, sdb: null as number | null, meuble: null as boolean | null };
  estival = { ville: '', categorie: null as string | null, chambres: null as number | null, lits: null as number | null, surface: null as number | null, front_de_mer: null as boolean | null };
  roi = { prix: null as number | null, loyer: null as number | null, nuit: null as number | null, nuits: 90 };

  resultat: Partial<Record<Mode, Resultat>> = {};
  roiResultat: any = null;
  erreurs: Record<string, string> = {};
  erreur: string | null = null;
  chargement = false;

  zones = { vente: [] as string[], location: [] as string[] };
  villesEstivales: string[] = [];
  rendements: any[] = [];
  rendementMedian: number | null = null;

  constructor(private readonly http: HttpClient) {}

  ngOnInit(): void {
    this.restaurer();
    for (const seg of ['vente', 'location'] as const) {
      this.http.get<any>(API_BASE + '/api/annonces/zones', { params: { collection: `clean_${seg}` } })
        .subscribe({ next: r => this.zones[seg] = (r.zones || []).map((z: any) => z.nom), error: () => {} });
    }
    this.http.get<any>(API_BASE + '/api/estival/villes').subscribe({ next: r => this.villesEstivales = r.villes || [], error: () => {} });
    this.http.get<any>(API_BASE + '/api/stats/marche').subscribe({
      next: r => { this.rendements = r.rendement_par_ville || []; this.rendementMedian = r.kpis?.rendement_brut_median_pct ?? null; },
      error: () => {},
    });
  }

  modeCourant() {
    return this.modes.find(m => m.id === this.mode)!;
  }

  changerMode(mode: Mode): void {
    this.mode = mode;
    this.erreurs = {};
    this.erreur = null;
    this.sauvegarder();
  }

  format(v: number): string {
    return nf(v);
  }

  position(r: Resultat): number {
    if (!r.bas || !r.haut || r.haut <= r.bas) return 50;
    return Math.min(96, Math.max(4, (r.valeur - r.bas) / (r.haut - r.bas) * 100));
  }

  classeRoi(label: string): string {
    return { excellent: 'badge-success', bon: 'badge-success', moyen: 'badge-warning', faible: 'badge-warning' }[label] || 'badge-danger';
  }

  texteVersRoi(): string {
    return { vente: 'Calculer la rentabilité avec ce prix', location: 'Utiliser ce loyer pour la rentabilité',
             estival: 'Utiliser ce prix par nuit pour la rentabilité', roi: '' }[this.mode];
  }

  versRentabilite(): void {
    const r = this.resultat[this.mode];
    if (!r) return;
    if (this.mode === 'vente') this.roi.prix = Math.round(r.valeur);
    if (this.mode === 'location') this.roi.loyer = Math.round(r.valeur);
    if (this.mode === 'estival') this.roi.nuit = Math.round(r.valeur);
    this.changerMode('roi');
    if (this.roi.prix && (this.roi.loyer || this.roi.nuit)) this.estimer();
  }

  simulerZone(z: any): void {
    this.roi.prix = Math.round(z.prix_median);
    this.roi.loyer = Math.round(z.loyer_median);
    this.roi.nuit = null;
    this.changerMode('roi');
    this.estimer();
  }

  reinitialiser(): void {
    const vides: Record<Mode, () => void> = {
      vente: () => this.vente = { zone: '', surface: null, type_bien: 'appartement', chambres: null, parking: false, ascenseur: false, piscine: false },
      location: () => this.location = { zone: '', surface: null, type_bien: 'appartement', chambres: null, sdb: null, meuble: null },
      estival: () => this.estival = { ville: '', categorie: null, chambres: null, lits: null, surface: null, front_de_mer: null },
      roi: () => { this.roi = { prix: null, loyer: null, nuit: null, nuits: 90 }; this.roiResultat = null; },
    };
    vides[this.mode]();
    delete this.resultat[this.mode];
    this.erreurs = {};
    this.erreur = null;
    this.sauvegarder();
  }

  private valider(): boolean {
    const e: Record<string, string> = {};
    const positif = (v: any) => v !== null && v !== undefined && v !== '' && Number(v) > 0;
    if (this.mode === 'vente' && !positif(this.vente.surface)) e['surface'] = 'La surface est nécessaire pour estimer un prix de vente.';
    if (this.mode === 'location' && this.location.surface !== null && !positif(this.location.surface)) e['surface'] = 'La surface doit être positive.';
    if (this.mode === 'estival' && !this.estival.ville) e['ville'] = 'Choisissez une ville.';
    if (this.mode === 'roi') {
      if (!positif(this.roi.prix)) e['prix'] = 'Indiquez le prix d\'achat.';
      if (!positif(this.roi.loyer) && !positif(this.roi.nuit)) e['revenus'] = 'Indiquez un loyer mensuel et/ou un prix par nuit.';
    }
    this.erreurs = e;
    return !Object.keys(e).length;
  }

  estimer(): void {
    if (!this.valider() || this.chargement) return;
    this.sauvegarder();
    this.chargement = true;
    this.erreur = null;
    const mode = this.mode;
    const p = (obj: Record<string, any>) => {
      let params = new HttpParams();
      Object.entries(obj).forEach(([k, v]) => { if (v !== null && v !== undefined && v !== '' && v !== false) params = params.set(k, String(v)); });
      return params;
    };
    const fin = () => this.chargement = false;
    const erreur = (err: any) => { this.erreur = this.messageErreur(err); fin(); };

    if (mode === 'vente') {
      const v = this.vente;
      this.http.get<any>(API_BASE + '/api/vente/estimation', { params: p({
        surface: v.surface, gouvernorat: v.zone.trim(), type_bien: v.type_bien, nb_chambres: v.chambres,
        has_parking: v.parking ? 1 : 0, has_ascenseur: v.ascenseur ? 1 : 0, has_piscine: v.piscine ? 1 : 0,
      }) }).subscribe({ next: r => {
        this.resultat.vente = { valeur: r.prix_estime, bas: r.intervalle_bas, haut: r.intervalle_haut, unite: 'TND',
          erreur: r.erreur_mediane_pct, zone: r.zone_reconnue ? this.titre(r.zone_reconnue) : null, zoneDemandee: v.zone.trim(),
          details: [{ libelle: 'Prix au m²', valeur: `${nf(r.prix_estime / Number(v.surface))} TND/m²` }] };
        fin();
      }, error: erreur });
    } else if (mode === 'location') {
      const l = this.location;
      this.http.get<any>(API_BASE + '/api/location/estimation', { params: p({
        surface: l.surface, ville: l.zone.trim(), type_bien: l.type_bien, nb_chambres: l.chambres, nb_sdb: l.sdb,
        meuble: l.meuble === null ? null : String(l.meuble),
      }) }).subscribe({ next: r => {
        const details = [];
        if (r.prix_m2_reference) details.push({ libelle: 'Loyer au m²', valeur: `${nf(r.prix_m2_reference, 1)} TND/m²` });
        if (r.n_annonces_entrainement) details.push({ libelle: 'Annonces de référence', valeur: nf(r.n_annonces_entrainement) });
        this.resultat.location = { valeur: r.loyer_estime, bas: r.intervalle_bas, haut: r.intervalle_haut, unite: 'TND/mois',
          erreur: r.erreur_mediane_pct, zone: r.zone_reconnue || null, zoneDemandee: l.zone.trim(), details };
        fin();
      }, error: erreur });
    } else if (mode === 'estival') {
      const e = this.estival;
      this.http.get<any>(API_BASE + '/api/estival/estimation', { params: p({
        ville: e.ville, categorie: e.categorie, nb_chambres: e.chambres, nb_lits: e.lits, surface: e.surface,
        front_de_mer: e.front_de_mer === null ? null : String(e.front_de_mer),
      }) }).subscribe({ next: r => {
        const details = [{ libelle: 'Logements comparables dans la ville', valeur: nf(r.nb_annonces) }];
        if (r.mediane_ville) details.push({ libelle: 'Médiane de la ville', valeur: `${nf(r.mediane_ville)} TND/nuit` });
        this.resultat.estival = { valeur: r.prix_nuit_estime, bas: r.intervalle_bas, haut: r.intervalle_haut, unite: 'TND/nuit',
          erreur: r.modele === 'M3-lightgbm' ? r.erreur_mediane_pct : null, zone: r.ville, details };
        fin();
      }, error: erreur });
    } else {
      this.http.get<any>(API_BASE + '/api/roi/calculer', { params: p({
        prix: this.roi.prix, loyer_mensuel: this.roi.loyer, prix_nuit: this.roi.nuit, nuits_an: this.roi.nuit ? this.roi.nuits : null,
      }) }).subscribe({ next: r => { this.roiResultat = r; fin(); }, error: erreur });
    }
  }

  private titre(s: string): string {
    return s.replace(/(^|\s)\S/g, c => c.toUpperCase());
  }

  /** Message lisible depuis une erreur HTTP FastAPI (detail texte ou liste de validation). */
  private messageErreur(err: any): string {
    const detail = err?.error?.detail;
    if (!err?.status) return 'Service momentanément indisponible, réessayez dans quelques instants.';
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail.length) return 'Valeur invalide : ' + detail.map((d: any) => (d.loc || []).slice(-1)[0]).join(', ');
    return `Erreur serveur (${err.status})`;
  }

  private sauvegarder(): void {
    try {
      sessionStorage.setItem(CLE_STOCKAGE, JSON.stringify({ mode: this.mode, vente: this.vente, location: this.location, estival: this.estival, roi: this.roi }));
    } catch { /* stockage indisponible : formulaires non conservés */ }
  }

  private restaurer(): void {
    try {
      const s = JSON.parse(sessionStorage.getItem(CLE_STOCKAGE) || 'null');
      if (!s) return;
      this.mode = s.mode || this.mode;
      Object.assign(this.vente, s.vente || {});
      Object.assign(this.location, s.location || {});
      Object.assign(this.estival, s.estival || {});
      Object.assign(this.roi, s.roi || {});
    } catch { /* ignoré */ }
  }
}
