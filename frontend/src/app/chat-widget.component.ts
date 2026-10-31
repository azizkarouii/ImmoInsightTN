import { Component, ElementRef, HostListener, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IconComponent } from './icon.component';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { API_BASE } from './api.config';

interface Source {
  titre?: string;
  prix?: number;
  unite?: string;
  ville?: string;
  gouvernorat?: string;
  url?: string;
  source?: string;
}

interface MessageChat {
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  erreur?: boolean;
}

const CLE_STOCKAGE = 'immoinsight-chat';
const SUGGESTIONS_PAR_DEFAUT = [
  "Quel est le loyer médian d'un S+2 à La Marsa ?",
  'Combien vaut un appartement de 120 m² à Ennasr ?',
  'Quelles opportunités à la vente cette semaine ?',
];

@Component({
  selector: 'app-chat-widget',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  template: `
    <button class="chat-fab" *ngIf="!ouvert" (click)="ouvrir()" aria-label="Ouvrir l'assistant ImmoInsight">
      <app-icon name="message"></app-icon>
    </button>

    <section class="chat-panel" *ngIf="ouvert" role="dialog" aria-label="Assistant ImmoInsight">
      <header class="chat-header">
        <div>
          <strong>Assistant ImmoInsight</strong>
          <span>Répond à partir des annonces de la plateforme</span>
        </div>
        <div class="chat-actions">
          <button *ngIf="messages.length" (click)="reinitialiser()" title="Nouvelle conversation" aria-label="Nouvelle conversation"><app-icon name="reset"></app-icon></button>
          <button (click)="ouvert = false" title="Fermer" aria-label="Fermer l'assistant"><app-icon name="x"></app-icon></button>
        </div>
      </header>

      <div class="chat-body" #corps>
        <div class="chat-welcome" *ngIf="!messages.length">
          <p>Bonjour ! Je réponds à vos questions sur le marché immobilier tunisien à partir des données collectées :
            prix, loyers, location estivale, estimations, rentabilité et alertes.</p>
          <div class="chat-suggestions">
            <button *ngFor="let s of suggestions" (click)="envoyer(s)">{{ s }}</button>
          </div>
        </div>

        <div *ngFor="let m of messages" class="chat-msg" [class.user]="m.role === 'user'" [class.erreur]="m.erreur">
          <div class="bulle" *ngIf="m.role === 'user'">{{ m.content }}</div>
          <div class="bulle" *ngIf="m.role === 'assistant'" [innerHTML]="formater(m.content)"></div>
          <div class="chat-sources" *ngIf="m.sources?.length">
            <span class="chat-sources-titre">Annonces consultées</span>
            <a *ngFor="let s of m.sources" [href]="s.url" target="_blank" rel="noopener noreferrer" class="chat-source">
              <span class="titre">{{ s.titre || 'Annonce' }}</span>
              <span class="meta">
                <strong *ngIf="s.prix">{{ s.prix | number:'1.0-0' }} {{ s.unite }}</strong>
                {{ lieu(s) }}<span *ngIf="s.source"> · {{ s.source }}</span>
              </span>
            </a>
          </div>
        </div>

        <div class="chat-msg" *ngIf="chargement">
          <div class="bulle typing" aria-label="L'assistant rédige sa réponse"><span></span><span></span><span></span></div>
        </div>
      </div>

      <form class="chat-input" (ngSubmit)="envoyer()">
        <textarea #champ [(ngModel)]="saisie" name="saisie" rows="1" maxlength="2000"
                  placeholder="Posez votre question…" (keydown)="clavier($event)" [disabled]="chargement"
                  aria-label="Votre question"></textarea>
        <button type="submit" [disabled]="chargement || !saisie.trim()" aria-label="Envoyer"><app-icon name="send"></app-icon></button>
      </form>
      <p class="chat-disclaimer">Réponses générées automatiquement à partir des annonces collectées. Les estimations sont indicatives.</p>
    </section>
  `,
  styles: []
})
export class ChatWidgetComponent implements OnInit {
  @ViewChild('corps') corps?: ElementRef<HTMLDivElement>;
  @ViewChild('champ') champ?: ElementRef<HTMLTextAreaElement>;

  ouvert = false;
  chargement = false;
  saisie = '';
  messages: MessageChat[] = [];
  suggestions = SUGGESTIONS_PAR_DEFAUT;

  constructor(private readonly http: HttpClient) {}

  ngOnInit(): void {
    try {
      const sauvegarde = sessionStorage.getItem(CLE_STOCKAGE);
      if (sauvegarde) this.messages = JSON.parse(sauvegarde);
    } catch {
      this.messages = [];
    }
  }

  @HostListener('document:keydown.escape')
  fermerAvecEchap(): void {
    this.ouvert = false;
  }

  ouvrir(): void {
    this.ouvert = true;
    if (this.suggestions === SUGGESTIONS_PAR_DEFAUT) {
      this.http.get<{ suggestions: string[] }>(API_BASE + '/api/chat/suggestions')
        .subscribe({ next: r => this.suggestions = r.suggestions?.length ? r.suggestions : SUGGESTIONS_PAR_DEFAUT, error: () => {} });
    }
    this.defiler();
    setTimeout(() => this.champ?.nativeElement.focus(), 50);
  }

  reinitialiser(): void {
    this.messages = [];
    this.sauvegarder();
  }

  clavier(event: KeyboardEvent): void {
    // Entrée envoie, Maj+Entrée ajoute une ligne
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.envoyer();
    }
  }

  envoyer(texte?: string): void {
    const question = (texte ?? this.saisie).trim();
    if (!question || this.chargement) return;
    this.saisie = '';
    this.messages.push({ role: 'user', content: question });
    this.chargement = true;
    this.defiler();

    // Historique envoyé : derniers échanges réussis, sans les messages d'erreur
    const historique = this.messages
      .filter(m => !m.erreur)
      .slice(-10)
      .map(m => ({ role: m.role, content: m.content }));

    this.http.post<{ reponse: string; sources: Source[] }>(API_BASE + '/api/chat', { messages: historique }).subscribe({
      next: r => {
        this.messages.push({ role: 'assistant', content: r.reponse, sources: r.sources });
        this.terminer();
      },
      error: err => {
        const detail = typeof err?.error?.detail === 'string' ? err.error.detail : null;
        this.messages.push({
          role: 'assistant',
          erreur: true,
          content: detail ?? (err?.status ? 'Une erreur est survenue, réessayez.' : 'Serveur injoignable, vérifiez votre connexion.'),
        });
        this.terminer();
      },
    });
  }

  lieu(s: Source): string {
    return [s.ville, s.gouvernorat].filter((v, i, a) => v && a.indexOf(v) === i).join(', ');
  }

  /** Markdown minimal (gras, listes, tableaux) sur un texte préalablement échappé. */
  formater(texte: string): string {
    const echapper = (t: string) => t.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));
    const enLigne = (t: string) => echapper(t)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*(?!\s)(.+?)\*(?!\*)/g, '$1<em>$2</em>');

    const lignes = texte.replaceAll('\r', '').split('\n');
    const html: string[] = [];
    let i = 0;
    while (i < lignes.length) {
      const ligne = lignes[i].trim();
      if (ligne.startsWith('|')) {
        const tableau: string[][] = [];
        while (i < lignes.length && lignes[i].trim().startsWith('|')) {
          const cellules = lignes[i].trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
          if (!cellules.every(c => /^:?-{2,}:?$/.test(c))) tableau.push(cellules);
          i++;
        }
        const [entete, ...corps] = tableau;
        html.push('<table><thead><tr>' + (entete || []).map(c => `<th>${enLigne(c)}</th>`).join('') + '</tr></thead><tbody>'
          + corps.map(r => '<tr>' + r.map(c => `<td>${enLigne(c)}</td>`).join('') + '</tr>').join('') + '</tbody></table>');
        continue;
      }
      if (/^[-*•]\s+/.test(ligne) || /^\d+[.)]\s+/.test(ligne)) {
        const ordonnee = /^\d+[.)]\s+/.test(ligne);
        const items: string[] = [];
        while (i < lignes.length && (/^[-*•]\s+/.test(lignes[i].trim()) || /^\d+[.)]\s+/.test(lignes[i].trim()))) {
          items.push(`<li>${enLigne(lignes[i].trim().replace(/^([-*•]|\d+[.)])\s+/, ''))}</li>`);
          i++;
        }
        html.push(ordonnee ? `<ol>${items.join('')}</ol>` : `<ul>${items.join('')}</ul>`);
        continue;
      }
      if (/^#{1,4}\s+/.test(ligne)) {
        html.push(`<p><strong>${enLigne(ligne.replace(/^#{1,4}\s+/, ''))}</strong></p>`);
      } else if (/^>\s?/.test(ligne)) {
        html.push(`<p class="note">${enLigne(ligne.replace(/^>\s?/, ''))}</p>`);
      } else if (ligne) {
        html.push(`<p>${enLigne(ligne)}</p>`);
      }
      i++;
    }
    return html.join('');
  }

  private terminer(): void {
    this.chargement = false;
    this.sauvegarder();
    this.defiler();
    setTimeout(() => this.champ?.nativeElement.focus(), 50);
  }

  private sauvegarder(): void {
    try {
      sessionStorage.setItem(CLE_STOCKAGE, JSON.stringify(this.messages.slice(-30)));
    } catch {
      // stockage indisponible (navigation privée) : la conversation reste en mémoire
    }
  }

  private defiler(): void {
    setTimeout(() => {
      const el = this.corps?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    }, 30);
  }
}
