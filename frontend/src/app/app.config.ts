import { ApplicationConfig, LOCALE_ID } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { registerLocaleData } from '@angular/common';
import localeFr from '@angular/common/locales/fr';

// Nombres et dates au format français dans tous les pipes (3 144 au lieu de 3,144)
registerLocaleData(localeFr, 'fr-FR');

export const appConfig: ApplicationConfig = {
  providers: [provideHttpClient(), { provide: LOCALE_ID, useValue: 'fr-FR' }]
};
