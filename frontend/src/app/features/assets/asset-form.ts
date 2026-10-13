import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, effect, inject, input, signal } from '@angular/core';
import {
  AbstractControl,
  FormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import {
  ASSET_TYPE_LABELS,
  ASSET_TYPES,
  AssetInput,
  AssetType,
} from '../../core/assets/asset.models';
import { AssetService } from '../../core/assets/asset.service';

/** The warranty cannot end before the equipment was bought. */
function datesInOrder(group: AbstractControl): ValidationErrors | null {
  const purchase = group.get('purchase_date')?.value as string;
  const warranty = group.get('warranty_expires_on')?.value as string;
  return purchase && warranty && warranty < purchase ? { warrantyBeforePurchase: true } : null;
}

const orNull = (value: string) => value.trim() || null;

@Component({
  selector: 'app-asset-form',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
  ],
  templateUrl: './asset-form.html',
  styleUrl: './asset-form.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AssetForm {
  /** Bound from the `:id` route param; absent when creating. */
  readonly id = input<string>();

  private readonly assets = inject(AssetService);
  private readonly router = inject(Router);

  protected readonly types = ASSET_TYPES;
  protected readonly typeLabels = ASSET_TYPE_LABELS;
  protected readonly saving = signal(false);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly form = inject(FormBuilder).nonNullable.group(
    {
      asset_tag: ['', [Validators.pattern(/^[A-Za-z0-9][A-Za-z0-9._-]{1,31}$/)]],
      type: ['laptop' as AssetType, Validators.required],
      manufacturer: ['', [Validators.required, Validators.maxLength(100)]],
      model: ['', [Validators.required, Validators.maxLength(100)]],
      serial_number: ['', Validators.maxLength(100)],
      location: ['', Validators.maxLength(100)],
      purchase_date: [''],
      warranty_expires_on: [''],
      notes: ['', Validators.maxLength(5000)],
    },
    { validators: datesInOrder },
  );

  protected get editing(): boolean {
    return this.id() !== undefined;
  }

  constructor() {
    effect(() => {
      const id = this.id();
      if (id !== undefined) void this.load(Number(id));
    });
  }

  private async load(id: number): Promise<void> {
    this.loading.set(true);
    try {
      const a = await firstValueFrom(this.assets.get(id));
      this.form.patchValue({
        asset_tag: a.asset_tag,
        type: a.type,
        manufacturer: a.manufacturer,
        model: a.model,
        serial_number: a.serial_number ?? '',
        location: a.location ?? '',
        purchase_date: a.purchase_date ?? '',
        warranty_expires_on: a.warranty_expires_on ?? '',
        notes: a.notes ?? '',
      });
      this.form.controls.asset_tag.disable(); // a tag is fixed once issued
    } catch {
      this.error.set('Could not load this asset.');
    } finally {
      this.loading.set(false);
    }
  }

  protected async submit(): Promise<void> {
    if (this.form.invalid || this.saving()) return;
    this.saving.set(true);
    this.error.set(null);

    const v = this.form.getRawValue();
    const input: AssetInput = {
      type: v.type,
      manufacturer: v.manufacturer.trim(),
      model: v.model.trim(),
      serial_number: orNull(v.serial_number),
      location: orNull(v.location),
      purchase_date: v.purchase_date || null,
      warranty_expires_on: v.warranty_expires_on || null,
      notes: orNull(v.notes),
    };

    try {
      const saved = this.editing
        ? await firstValueFrom(this.assets.update(Number(this.id()), input))
        : await firstValueFrom(this.assets.create({ ...input, asset_tag: orNull(v.asset_tag) }));
      await this.router.navigate(['/assets', saved.id]);
    } catch (err) {
      this.error.set(
        err instanceof HttpErrorResponse && err.status === 409
          ? 'An asset with that tag or serial number already exists.'
          : 'Could not save the asset. Please check the details and try again.',
      );
      this.saving.set(false);
    }
  }
}
