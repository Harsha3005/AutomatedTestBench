"""
Seed ISO 4064 Q-point calibration data for all meter sizes and classes.

Usage:
    python manage.py seed_iso4064          # Seed missing entries only
    python manage.py seed_iso4064 --reset  # Delete all & re-seed

References:
    - ISO 4064-1:2014 / OIML R 49-1 (R-class system)
    - IS 779:1994 / old ISO 4064:1993 (Class A/B/C system)

Mapping (approximate):
    Class A  ≈  R40   (least stringent, narrow flow range)
    Class B  ≈  R100  (medium, standard domestic meters)
    Class C  ≈  R200  (most stringent, wide flow range)

Q-point definitions (ISO 4064-1:2014):
    Q1 = Minimum flow rate           (Lower zone, MPE ±5%)
    Q2 = Transitional flow rate      (Upper zone, MPE ±2%)
    Q3 = Permanent flow rate         (Upper zone, MPE ±2%)
    Q4 = Overload flow rate          (Upper zone, MPE ±2%)
    Q5 = Extended minimum            (Lower zone, MPE ±5%)
    Q6 = Intermediate lower          (Lower zone, MPE ±5%)
    Q7 = Intermediate upper          (Upper zone, MPE ±2%)
    Q8 = Extended overload           (Upper zone, MPE ±2%)

NOTE: The values below are standard reference values. IIITB engineers
should review and adjust flow rates, test volumes, and durations as
per their specific test bench capabilities and standard requirements.
"""

from django.core.management.base import BaseCommand
from testing.models import ISO4064Standard


# ──────────────────────────────────────────────────────────────────
# DATA TABLE
# Format: (meter_size, meter_class, q_point, flow_rate_lph,
#           test_volume_l, duration_s, mpe_pct, zone)
# ──────────────────────────────────────────────────────────────────

DATA = [
    # ================================================================
    # DN15 (Qn = 1500 L/h for Class A/B/C; Q3 = varies by R-class)
    # ================================================================

    # --- DN15 Class A (≈ R40) ---
    ('DN15', 'A', 'Q1', 25.0,   2.0,  288,  5.0, 'Lower'),
    ('DN15', 'A', 'Q2', 40.0,   4.0,  360,  2.0, 'Upper'),
    ('DN15', 'A', 'Q3', 100.0,  10.0, 360,  2.0, 'Upper'),
    ('DN15', 'A', 'Q4', 1600.0, 100.0, 225, 2.0, 'Upper'),
    ('DN15', 'A', 'Q5', 12.5,   1.0,  288,  5.0, 'Lower'),
    ('DN15', 'A', 'Q6', 31.25,  3.0,  346,  5.0, 'Lower'),
    ('DN15', 'A', 'Q7', 50.0,   5.0,  360,  2.0, 'Upper'),
    ('DN15', 'A', 'Q8', 2000.0, 120.0, 216, 2.0, 'Upper'),

    # --- DN15 Class B (≈ R100) ---
    ('DN15', 'B', 'Q1', 10.0,   1.0,  360,  5.0, 'Lower'),
    ('DN15', 'B', 'Q2', 16.0,   1.6,  360,  2.0, 'Upper'),
    ('DN15', 'B', 'Q3', 100.0,  10.0, 360,  2.0, 'Upper'),
    ('DN15', 'B', 'Q4', 1600.0, 100.0, 225, 2.0, 'Upper'),
    ('DN15', 'B', 'Q5', 5.0,    0.5,  360,  5.0, 'Lower'),
    ('DN15', 'B', 'Q6', 12.5,   1.25, 360,  5.0, 'Lower'),
    ('DN15', 'B', 'Q7', 50.0,   5.0,  360,  2.0, 'Upper'),
    ('DN15', 'B', 'Q8', 2000.0, 120.0, 216, 2.0, 'Upper'),

    # --- DN15 Class C (≈ R315) ---
    ('DN15', 'C', 'Q1', 3.175,  0.25, 284,  5.0, 'Lower'),
    ('DN15', 'C', 'Q2', 5.0,    0.5,  360,  2.0, 'Upper'),
    ('DN15', 'C', 'Q3', 100.0,  10.0, 360,  2.0, 'Upper'),
    ('DN15', 'C', 'Q4', 1600.0, 100.0, 225, 2.0, 'Upper'),
    ('DN15', 'C', 'Q5', 1.6,    0.15, 338,  5.0, 'Lower'),
    ('DN15', 'C', 'Q6', 4.0,    0.4,  360,  5.0, 'Lower'),
    ('DN15', 'C', 'Q7', 50.0,   5.0,  360,  2.0, 'Upper'),
    ('DN15', 'C', 'Q8', 2000.0, 120.0, 216, 2.0, 'Upper'),

    # --- DN15 R80 ---
    ('DN15', 'R80', 'Q1', 12.5,  1.0,  288,  5.0, 'Lower'),
    ('DN15', 'R80', 'Q2', 20.0,  2.0,  360,  2.0, 'Upper'),
    ('DN15', 'R80', 'Q3', 100.0, 10.0, 360,  2.0, 'Upper'),
    ('DN15', 'R80', 'Q4', 1600.0, 100.0, 225, 2.0, 'Upper'),
    ('DN15', 'R80', 'Q5', 6.25,  0.5,  288,  5.0, 'Lower'),
    ('DN15', 'R80', 'Q6', 16.0,  1.6,  360,  5.0, 'Lower'),
    ('DN15', 'R80', 'Q7', 50.0,  5.0,  360,  2.0, 'Upper'),
    ('DN15', 'R80', 'Q8', 2000.0, 120.0, 216, 2.0, 'Upper'),

    # --- DN15 R100 (already existed, re-included for completeness) ---
    ('DN15', 'R100', 'Q1', 10.0,   1.0,  360,  5.0, 'Lower'),
    ('DN15', 'R100', 'Q2', 16.0,   1.6,  360,  2.0, 'Upper'),
    ('DN15', 'R100', 'Q3', 100.0,  10.0, 360,  2.0, 'Upper'),
    ('DN15', 'R100', 'Q4', 1600.0, 100.0, 225, 2.0, 'Upper'),
    ('DN15', 'R100', 'Q5', 5.0,    0.5,  360,  5.0, 'Lower'),
    ('DN15', 'R100', 'Q6', 12.5,   1.25, 360,  5.0, 'Lower'),
    ('DN15', 'R100', 'Q7', 50.0,   5.0,  360,  2.0, 'Upper'),
    ('DN15', 'R100', 'Q8', 2000.0, 120.0, 216, 2.0, 'Upper'),

    # --- DN15 R160 (already existed, re-included for completeness) ---
    ('DN15', 'R160', 'Q1', 6.25,   0.5,  288,  5.0, 'Lower'),
    ('DN15', 'R160', 'Q2', 10.0,   1.0,  360,  2.0, 'Upper'),
    ('DN15', 'R160', 'Q3', 100.0,  10.0, 360,  2.0, 'Upper'),
    ('DN15', 'R160', 'Q4', 1600.0, 100.0, 225, 2.0, 'Upper'),
    ('DN15', 'R160', 'Q5', 3.125,  0.25, 288,  5.0, 'Lower'),
    ('DN15', 'R160', 'Q6', 8.0,    0.8,  360,  5.0, 'Lower'),
    ('DN15', 'R160', 'Q7', 50.0,   5.0,  360,  2.0, 'Upper'),
    ('DN15', 'R160', 'Q8', 2000.0, 120.0, 216, 2.0, 'Upper'),

    # --- DN15 R200 ---
    ('DN15', 'R200', 'Q1', 5.0,    0.4,  288,  5.0, 'Lower'),
    ('DN15', 'R200', 'Q2', 8.0,    0.8,  360,  2.0, 'Upper'),
    ('DN15', 'R200', 'Q3', 100.0,  10.0, 360,  2.0, 'Upper'),
    ('DN15', 'R200', 'Q4', 1600.0, 100.0, 225, 2.0, 'Upper'),
    ('DN15', 'R200', 'Q5', 2.5,    0.2,  288,  5.0, 'Lower'),
    ('DN15', 'R200', 'Q6', 6.4,    0.64, 360,  5.0, 'Lower'),
    ('DN15', 'R200', 'Q7', 50.0,   5.0,  360,  2.0, 'Upper'),
    ('DN15', 'R200', 'Q8', 2000.0, 120.0, 216, 2.0, 'Upper'),

    # ================================================================
    # DN20 (Qn = 2500 L/h for Class A/B/C; Q3 scales accordingly)
    # ================================================================

    # --- DN20 Class A (≈ R40) ---
    ('DN20', 'A', 'Q1', 50.0,   4.0,  288,  5.0, 'Lower'),
    ('DN20', 'A', 'Q2', 80.0,   8.0,  360,  2.0, 'Upper'),
    ('DN20', 'A', 'Q3', 200.0,  20.0, 360,  2.0, 'Upper'),
    ('DN20', 'A', 'Q4', 3200.0, 200.0, 225, 2.0, 'Upper'),
    ('DN20', 'A', 'Q5', 25.0,   2.0,  288,  5.0, 'Lower'),
    ('DN20', 'A', 'Q6', 62.5,   6.0,  346,  5.0, 'Lower'),
    ('DN20', 'A', 'Q7', 100.0,  10.0, 360,  2.0, 'Upper'),
    ('DN20', 'A', 'Q8', 4000.0, 160.0, 144, 2.0, 'Upper'),

    # --- DN20 Class B (≈ R100) ---
    ('DN20', 'B', 'Q1', 20.0,   2.0,  360,  5.0, 'Lower'),
    ('DN20', 'B', 'Q2', 32.0,   3.2,  360,  2.0, 'Upper'),
    ('DN20', 'B', 'Q3', 200.0,  20.0, 360,  2.0, 'Upper'),
    ('DN20', 'B', 'Q4', 3200.0, 200.0, 225, 2.0, 'Upper'),
    ('DN20', 'B', 'Q5', 10.0,   1.0,  360,  5.0, 'Lower'),
    ('DN20', 'B', 'Q6', 25.0,   2.5,  360,  5.0, 'Lower'),
    ('DN20', 'B', 'Q7', 100.0,  10.0, 360,  2.0, 'Upper'),
    ('DN20', 'B', 'Q8', 4000.0, 160.0, 144, 2.0, 'Upper'),

    # --- DN20 Class C (≈ R315) ---
    ('DN20', 'C', 'Q1', 6.35,   0.5,  284,  5.0, 'Lower'),
    ('DN20', 'C', 'Q2', 10.0,   1.0,  360,  2.0, 'Upper'),
    ('DN20', 'C', 'Q3', 200.0,  20.0, 360,  2.0, 'Upper'),
    ('DN20', 'C', 'Q4', 3200.0, 200.0, 225, 2.0, 'Upper'),
    ('DN20', 'C', 'Q5', 3.175,  0.25, 284,  5.0, 'Lower'),
    ('DN20', 'C', 'Q6', 8.0,    0.8,  360,  5.0, 'Lower'),
    ('DN20', 'C', 'Q7', 100.0,  10.0, 360,  2.0, 'Upper'),
    ('DN20', 'C', 'Q8', 4000.0, 160.0, 144, 2.0, 'Upper'),

    # --- DN20 R80 ---
    ('DN20', 'R80', 'Q1', 25.0,   2.0,  288,  5.0, 'Lower'),
    ('DN20', 'R80', 'Q2', 40.0,   4.0,  360,  2.0, 'Upper'),
    ('DN20', 'R80', 'Q3', 200.0,  20.0, 360,  2.0, 'Upper'),
    ('DN20', 'R80', 'Q4', 3200.0, 200.0, 225, 2.0, 'Upper'),
    ('DN20', 'R80', 'Q5', 12.5,   1.0,  288,  5.0, 'Lower'),
    ('DN20', 'R80', 'Q6', 32.0,   3.2,  360,  5.0, 'Lower'),
    ('DN20', 'R80', 'Q7', 100.0,  10.0, 360,  2.0, 'Upper'),
    ('DN20', 'R80', 'Q8', 4000.0, 160.0, 144, 2.0, 'Upper'),

    # --- DN20 R100 (already existed) ---
    ('DN20', 'R100', 'Q1', 20.0,   2.0,  360,  5.0, 'Lower'),
    ('DN20', 'R100', 'Q2', 32.0,   3.2,  360,  2.0, 'Upper'),
    ('DN20', 'R100', 'Q3', 200.0,  20.0, 360,  2.0, 'Upper'),
    ('DN20', 'R100', 'Q4', 3200.0, 200.0, 225, 2.0, 'Upper'),
    ('DN20', 'R100', 'Q5', 10.0,   1.0,  360,  5.0, 'Lower'),
    ('DN20', 'R100', 'Q6', 25.0,   2.5,  360,  5.0, 'Lower'),
    ('DN20', 'R100', 'Q7', 100.0,  10.0, 360,  2.0, 'Upper'),
    ('DN20', 'R100', 'Q8', 4000.0, 160.0, 144, 2.0, 'Upper'),

    # --- DN20 R160 (already existed) ---
    ('DN20', 'R160', 'Q1', 12.5,   1.0,  288,  5.0, 'Lower'),
    ('DN20', 'R160', 'Q2', 20.0,   2.0,  360,  2.0, 'Upper'),
    ('DN20', 'R160', 'Q3', 200.0,  20.0, 360,  2.0, 'Upper'),
    ('DN20', 'R160', 'Q4', 3200.0, 200.0, 225, 2.0, 'Upper'),
    ('DN20', 'R160', 'Q5', 6.25,   0.5,  288,  5.0, 'Lower'),
    ('DN20', 'R160', 'Q6', 16.0,   1.6,  360,  5.0, 'Lower'),
    ('DN20', 'R160', 'Q7', 100.0,  10.0, 360,  2.0, 'Upper'),
    ('DN20', 'R160', 'Q8', 4000.0, 160.0, 144, 2.0, 'Upper'),

    # --- DN20 R200 ---
    ('DN20', 'R200', 'Q1', 10.0,   0.8,  288,  5.0, 'Lower'),
    ('DN20', 'R200', 'Q2', 16.0,   1.6,  360,  2.0, 'Upper'),
    ('DN20', 'R200', 'Q3', 200.0,  20.0, 360,  2.0, 'Upper'),
    ('DN20', 'R200', 'Q4', 3200.0, 200.0, 225, 2.0, 'Upper'),
    ('DN20', 'R200', 'Q5', 5.0,    0.4,  288,  5.0, 'Lower'),
    ('DN20', 'R200', 'Q6', 12.8,   1.28, 360,  5.0, 'Lower'),
    ('DN20', 'R200', 'Q7', 100.0,  10.0, 360,  2.0, 'Upper'),
    ('DN20', 'R200', 'Q8', 4000.0, 160.0, 144, 2.0, 'Upper'),

    # ================================================================
    # DN25 (Qn = 3500 L/h for Class A/B/C; Q3 scales accordingly)
    # ================================================================

    # --- DN25 Class A (≈ R40) ---
    ('DN25', 'A', 'Q1', 78.125,  6.0,  277,  5.0, 'Lower'),
    ('DN25', 'A', 'Q2', 125.0,   12.0, 346,  2.0, 'Upper'),
    ('DN25', 'A', 'Q3', 312.5,   30.0, 346,  2.0, 'Upper'),
    ('DN25', 'A', 'Q4', 5000.0,  160.0, 115, 2.0, 'Upper'),
    ('DN25', 'A', 'Q5', 39.0,    3.0,  277,  5.0, 'Lower'),
    ('DN25', 'A', 'Q6', 100.0,   10.0, 360,  5.0, 'Lower'),
    ('DN25', 'A', 'Q7', 156.25,  15.0, 346,  2.0, 'Upper'),
    ('DN25', 'A', 'Q8', 6250.0,  180.0, 104, 2.0, 'Upper'),

    # --- DN25 Class B (≈ R100) ---
    ('DN25', 'B', 'Q1', 31.25,   3.0,  346,  5.0, 'Lower'),
    ('DN25', 'B', 'Q2', 50.0,    5.0,  360,  2.0, 'Upper'),
    ('DN25', 'B', 'Q3', 312.5,   30.0, 346,  2.0, 'Upper'),
    ('DN25', 'B', 'Q4', 5000.0,  160.0, 115, 2.0, 'Upper'),
    ('DN25', 'B', 'Q5', 15.625,  1.5,  346,  5.0, 'Lower'),
    ('DN25', 'B', 'Q6', 40.0,    4.0,  360,  5.0, 'Lower'),
    ('DN25', 'B', 'Q7', 156.25,  15.0, 346,  2.0, 'Upper'),
    ('DN25', 'B', 'Q8', 6250.0,  180.0, 104, 2.0, 'Upper'),

    # --- DN25 Class C (≈ R315) ---
    ('DN25', 'C', 'Q1', 9.92,    0.75, 272,  5.0, 'Lower'),
    ('DN25', 'C', 'Q2', 15.625,  1.5,  346,  2.0, 'Upper'),
    ('DN25', 'C', 'Q3', 312.5,   30.0, 346,  2.0, 'Upper'),
    ('DN25', 'C', 'Q4', 5000.0,  160.0, 115, 2.0, 'Upper'),
    ('DN25', 'C', 'Q5', 5.0,     0.4,  288,  5.0, 'Lower'),
    ('DN25', 'C', 'Q6', 12.5,    1.25, 360,  5.0, 'Lower'),
    ('DN25', 'C', 'Q7', 156.25,  15.0, 346,  2.0, 'Upper'),
    ('DN25', 'C', 'Q8', 6250.0,  180.0, 104, 2.0, 'Upper'),

    # --- DN25 R80 ---
    ('DN25', 'R80', 'Q1', 39.0,    3.0,  277,  5.0, 'Lower'),
    ('DN25', 'R80', 'Q2', 62.5,    6.0,  346,  2.0, 'Upper'),
    ('DN25', 'R80', 'Q3', 312.5,   30.0, 346,  2.0, 'Upper'),
    ('DN25', 'R80', 'Q4', 5000.0,  160.0, 115, 2.0, 'Upper'),
    ('DN25', 'R80', 'Q5', 19.5,    1.5,  277,  5.0, 'Lower'),
    ('DN25', 'R80', 'Q6', 50.0,    5.0,  360,  5.0, 'Lower'),
    ('DN25', 'R80', 'Q7', 156.25,  15.0, 346,  2.0, 'Upper'),
    ('DN25', 'R80', 'Q8', 6250.0,  180.0, 104, 2.0, 'Upper'),

    # --- DN25 R100 (already existed) ---
    ('DN25', 'R100', 'Q1', 31.25,   3.0,  346,  5.0, 'Lower'),
    ('DN25', 'R100', 'Q2', 50.0,    5.0,  360,  2.0, 'Upper'),
    ('DN25', 'R100', 'Q3', 312.5,   30.0, 346,  2.0, 'Upper'),
    ('DN25', 'R100', 'Q4', 5000.0,  160.0, 115, 2.0, 'Upper'),
    ('DN25', 'R100', 'Q5', 15.625,  1.5,  346,  5.0, 'Lower'),
    ('DN25', 'R100', 'Q6', 40.0,    4.0,  360,  5.0, 'Lower'),
    ('DN25', 'R100', 'Q7', 156.25,  15.0, 346,  2.0, 'Upper'),
    ('DN25', 'R100', 'Q8', 6250.0,  180.0, 104, 2.0, 'Upper'),

    # --- DN25 R160 (already existed) ---
    ('DN25', 'R160', 'Q1', 19.5,    1.5,  277,  5.0, 'Lower'),
    ('DN25', 'R160', 'Q2', 31.25,   3.0,  346,  2.0, 'Upper'),
    ('DN25', 'R160', 'Q3', 312.5,   30.0, 346,  2.0, 'Upper'),
    ('DN25', 'R160', 'Q4', 5000.0,  160.0, 115, 2.0, 'Upper'),
    ('DN25', 'R160', 'Q5', 9.75,    0.75, 277,  5.0, 'Lower'),
    ('DN25', 'R160', 'Q6', 25.0,    2.5,  360,  5.0, 'Lower'),
    ('DN25', 'R160', 'Q7', 156.25,  15.0, 346,  2.0, 'Upper'),
    ('DN25', 'R160', 'Q8', 6250.0,  180.0, 104, 2.0, 'Upper'),

    # --- DN25 R200 ---
    ('DN25', 'R200', 'Q1', 15.625,  1.2,  277,  5.0, 'Lower'),
    ('DN25', 'R200', 'Q2', 25.0,    2.5,  360,  2.0, 'Upper'),
    ('DN25', 'R200', 'Q3', 312.5,   30.0, 346,  2.0, 'Upper'),
    ('DN25', 'R200', 'Q4', 5000.0,  160.0, 115, 2.0, 'Upper'),
    ('DN25', 'R200', 'Q5', 7.8,     0.6,  277,  5.0, 'Lower'),
    ('DN25', 'R200', 'Q6', 20.0,    2.0,  360,  5.0, 'Lower'),
    ('DN25', 'R200', 'Q7', 156.25,  15.0, 346,  2.0, 'Upper'),
    ('DN25', 'R200', 'Q8', 6250.0,  180.0, 104, 2.0, 'Upper'),

]


class Command(BaseCommand):
    help = 'Seed ISO 4064 Q-point calibration data for all meter sizes and classes'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help='Delete all existing ISO 4064 data and re-seed from scratch',
        )

    def handle(self, *args, **options):
        if options['reset']:
            deleted, _ = ISO4064Standard.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'Deleted {deleted} existing records.'))

        created = 0
        updated = 0
        for row in DATA:
            size, cls, qpt, flow, vol, dur, mpe, zone = row
            obj, was_created = ISO4064Standard.objects.update_or_create(
                meter_size=size,
                meter_class=cls,
                q_point=qpt,
                defaults={
                    'flow_rate_lph': flow,
                    'test_volume_l': vol,
                    'duration_s': dur,
                    'mpe_pct': mpe,
                    'zone': zone,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        total = ISO4064Standard.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f'Done: {created} created, {updated} updated. Total records: {total}'
        ))
