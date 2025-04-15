#!/usr/bin/env python
from django.core.management.base import BaseCommand
from portfolio.tasks import update_all_stocks_daily
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Schedule a Cloud Task to update all stocks in the database'

    def handle(self, *args, **options):
        """
        Schedule a Cloud Task to refresh all stock data
        This is meant to be called by a scheduler (e.g., cron job or Cloud Scheduler)
        """
        self.stdout.write('Scheduling daily stock update task...')
        
        try:
            success = update_all_stocks_daily()
            
            if success:
                self.stdout.write(self.style.SUCCESS('Successfully scheduled stock update task'))
            else:
                self.stdout.write(self.style.ERROR('Failed to schedule stock update task'))
                
        except Exception as e:
            logger.exception('Error scheduling stock update task')
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}')) 