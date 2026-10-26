# -*- coding: utf-8 -*-
import datetime

import pytz


def day_bounds_utc(env, date_start, date_end=None):
    """Bornes UTC (naïves) d'une période de jours entiers, calculées dans le
    fuseau horaire de l'utilisateur : de 00:00:00 le premier jour à 23:59:59 le dernier."""
    date_end = date_end or date_start
    tz = pytz.timezone(env.context.get('tz') or env.user.tz or 'UTC')

    def to_utc(day, t):
        return tz.localize(datetime.datetime.combine(day, t)).astimezone(pytz.utc).replace(tzinfo=None)

    return to_utc(date_start, datetime.time.min), to_utc(date_end, datetime.time.max)
