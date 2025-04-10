from django.db import models

# Create your models here.
class spinfo(models.Model):
    year = models.IntegerField()
    avg_closing_price = models.DecimalField(max_digits=15, decimal_places=2)
    year_open = models.DecimalField(max_digits=15, decimal_places=2)
    year_high = models.DecimalField(max_digits=15, decimal_places=2)
    year_low = models.DecimalField(max_digits=15, decimal_places=2)
    year_close = models.DecimalField(max_digits=15, decimal_places=2)
    spreturn = models.DecimalField(max_digits=15, decimal_places=2)
    return_divident = models.DecimalField(max_digits=15, decimal_places=2)
    inflation = models.DecimalField(max_digits=15, decimal_places=2)
