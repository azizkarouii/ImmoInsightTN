import { ChangeDetectionStrategy, Component, Input } from '@angular/core';

// Tracés Lucide (https://lucide.dev, licence ISC), 24×24, trait 2 px.
// Icônes vectorielles à la place des emojis : rendu identique sur tous les systèmes,
// couleur héritée du texte (currentColor) et taille pilotée par le CSS.
// Les tracés sont écrits dans le template : aucun HTML injecté, la protection XSS d'Angular reste active.
@Component({
  selector: 'app-icon',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'icon', 'aria-hidden': 'true' },
  template: `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      @switch (name) {
        @case ('house') {
          <path d="M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8"/>
          <path d="M3 10a2 2 0 0 1 .709-1.528l7-5.999a2 2 0 0 1 2.582 0l7 5.999A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
        }
        @case ('map') {
          <path d="M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0z"/>
          <path d="M15 5.764v15"/><path d="M9 3.236v15"/>
        }
        @case ('chart') {
          <path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>
        }
        @case ('calculator') {
          <rect width="16" height="20" x="4" y="2" rx="2"/><path d="M8 6h8"/><path d="M16 14v4"/>
          <path d="M16 10h.01"/><path d="M12 10h.01"/><path d="M8 10h.01"/><path d="M12 14h.01"/>
          <path d="M8 14h.01"/><path d="M12 18h.01"/><path d="M8 18h.01"/>
        }
        @case ('bell') {
          <path d="M10.268 21a2 2 0 0 0 3.464 0"/>
          <path d="M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326"/>
        }
        @case ('message') { <path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/> }
        @case ('reset') { <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/> }
        @case ('x') { <path d="M18 6 6 18"/><path d="m6 6 12 12"/> }
        @case ('send') { <path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/> }
        @case ('search') { <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/> }
        @case ('tag') {
          <path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z"/>
          <circle cx="7.5" cy="7.5" r=".5" fill="currentColor"/>
        }
        @case ('waves') {
          <path d="M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/>
          <path d="M2 12c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/>
          <path d="M2 18c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/>
        }
        @case ('trending-up') { <path d="M22 7 13.5 15.5 8.5 10.5 2 17"/><path d="M16 7h6v6"/> }
        @case ('trending-down') { <path d="M22 17 13.5 8.5 8.5 13.5 2 7"/><path d="M16 17h6v-6"/> }
        @case ('sparkles') {
          <path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/>
        }
        @case ('gem') { <path d="M6 3h12l4 6-10 13L2 9Z"/><path d="M11 3 8 9l4 13 4-13-3-6"/><path d="M2 9h20"/> }
        @case ('ban') { <circle cx="12" cy="12" r="10"/><path d="m4.9 4.9 14.2 14.2"/> }
        @case ('alert') {
          <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>
        }
        @case ('pin') {
          <path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/>
          <circle cx="12" cy="10" r="3"/>
        }
        @case ('flame') {
          <path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>
        }
        @case ('chevron-up') { <path d="m18 15-6-6-6 6"/> }
        @case ('chevron-down') { <path d="m6 9 6 6 6-6"/> }
        @case ('chevrons-up-down') { <path d="m7 15 5 5 5-5"/><path d="m7 9 5-5 5 5"/> }
      }
    </svg>
  `,
})
export class IconComponent {
  @Input({ required: true }) name!: string;
}
