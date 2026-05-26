"""Canned Garmin API responses for unit + integration tests.

Based on real Garmin API shapes as of May 2026 (python-garminconnect>=0.3.4).
Update when the `garminconnect` library bumps its response schemas.

Kept as Python dicts (not JSON files) so they're refactorable when Garmin
schemas drift — touching a key here surfaces every consumer at lint-time
instead of failing only at runtime when JSON is loaded.

Every constant is dated `_2026_05_22` to match the canonical fixed date
used across the test suite (`tests/conftest.py::fixed_now`).
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "ACTIVITIES_LAST_10",
    "ACTIVITY_99001_DETAIL",
    "ACTIVITY_99001_SPLITS",
    "BODY_BATTERY_2026_05_22",
    "HRV_2026_05_22",
    "RHR_2026_05_22",
    "SLEEP_2026_05_22",
    "STATS_2026_05_22",
    "TR_2026_05_22",
    "VO2_2026_05_22",
]


# ---------------------------------------------------------------------------
# get_stats(date) — Garmin daily-summary endpoint
# ---------------------------------------------------------------------------
STATS_2026_05_22: dict[str, Any] = {
    "userProfileId": 12345678,
    "totalKilocalories": 2241,
    "activeKilocalories": 621,
    "bmrKilocalories": 1620,
    "wellnessKilocalories": 2241,
    "burnedKilocalories": None,
    "consumedKilocalories": 0,
    "remainingKilocalories": 2241,
    "totalSteps": 8423,
    "totalDistanceMeters": 6789,
    "wellnessDistanceMeters": 6789,
    "wellnessActiveKilocalories": 621,
    "netCalorieGoal": None,
    "dailyStepGoal": 8000,
    "wellnessStartTimeGmt": "2026-05-22T07:00:00.0",
    "wellnessEndTimeGmt": "2026-05-23T06:59:59.0",
    "wellnessStartTimeLocal": "2026-05-22T00:00:00.0",
    "wellnessEndTimeLocal": "2026-05-22T23:59:59.0",
    "durationInMilliseconds": 86400000,
    "wellnessDescription": None,
    "highlyActiveSeconds": 1380,
    "activeSeconds": 6240,
    "sedentarySeconds": 39600,
    "sleepingSeconds": 26640,
    "moderateIntensityMinutes": 35,
    "vigorousIntensityMinutes": 18,
    "floorsAscendedInMeters": 21.336,
    "floorsDescendedInMeters": 21.336,
    "floorsAscended": 7.0,
    "floorsDescended": 7.0,
    "intensityMinutesGoal": 150,
    "userFloorsAscendedGoal": 10,
    "minHeartRate": 45,
    "maxHeartRate": 171,
    "restingHeartRate": 47,
    "lastSevenDaysAvgRestingHeartRate": 48,
    "source": "GARMIN",
    "averageStressLevel": 28,
    "maxStressLevel": 71,
    "stressDuration": 28800,
    "restStressDuration": 18000,
    "activityStressDuration": 7200,
    "uncategorizedStressDuration": 1800,
    "totalStressDuration": 55800,
    "lowStressDuration": 18000,
    "mediumStressDuration": 8400,
    "highStressDuration": 2400,
    "stressDurationInSeconds": 28800,
    "stressQualifier": "BALANCED",
    "measurableAwakeDuration": 0,
    "measurableAsleepDuration": 26640,
    "lastSyncTimestampGMT": "2026-05-22T23:55:13.0",
    "bodyBatteryChargedValue": 64,
    "bodyBatteryDrainedValue": 51,
    "bodyBatteryHighestValue": 89,
    "bodyBatteryLowestValue": 28,
    "bodyBatteryMostRecentValue": 56,
    "bodyBatteryDuringSleep": 64,
    "bodyBatteryVersion": 2.0,
    "abnormalHeartRateAlertsCount": 0,
    "averageSpo2": 96,
    "lowestSpo2": 91,
    "latestSpo2": 95,
    "latestSpo2ReadingTimeGmt": "2026-05-22T05:23:00.0",
    "latestSpo2ReadingTimeLocal": "2026-05-21T22:23:00.0",
    "averageMonitoringEnvironmentAltitude": 124.0,
    "restingCaloriesFromActivity": 0,
    "avgWakingRespirationValue": 13.5,
    "highestRespirationValue": 19.0,
    "lowestRespirationValue": 10.0,
    "latestRespirationValue": 14.0,
    "latestRespirationTimeGMT": "2026-05-22T23:50:00.0",
}


# ---------------------------------------------------------------------------
# get_sleep_data(date) — Garmin sleep endpoint
# ---------------------------------------------------------------------------
SLEEP_2026_05_22: dict[str, Any] = {
    "dailySleepDTO": {
        "id": 1779456000000,
        "userProfilePK": 12345678,
        "calendarDate": "2026-05-22",
        "sleepTimeSeconds": 26640,  # 7.4 hours
        "napTimeSeconds": 0,
        "sleepWindowConfirmed": True,
        "sleepWindowConfirmationType": "enhanced_confirmed_final",
        "sleepStartTimestampGMT": 1779426000000,
        "sleepEndTimestampGMT": 1779452640000,
        "sleepStartTimestampLocal": 1779400800000,
        "sleepEndTimestampLocal": 1779427440000,
        "autoSleepStartTimestampGMT": 1779426000000,
        "autoSleepEndTimestampGMT": 1779452640000,
        "sleepQualityTypePK": None,
        "sleepResultTypePK": None,
        "unmeasurableSleepSeconds": 0,
        "deepSleepSeconds": 5400,  # 1.5 h
        "lightSleepSeconds": 14400,  # 4.0 h
        "remSleepSeconds": 5040,  # 1.4 h
        "awakeSleepSeconds": 1800,  # 0.5 h
        "deviceRemCapable": True,
        "retro": False,
        "sleepFromDevice": True,
        "averageRespirationValue": 13.5,
        "lowestRespirationValue": 11.0,
        "highestRespirationValue": 16.0,
        "awakeCount": 3,
        "avgSleepStress": 22.0,
        "ageGroup": "ADULT",
        "sleepScoreFeedback": "POSITIVE_LONGER_THAN_RECOMMENDED",
        "sleepScoreInsight": "NONE",
        "sleepScores": {
            "overall": {"value": 82, "qualifierKey": "GOOD"},
            "totalDuration": {"qualifierKey": "GOOD"},
            "stress": {"qualifierKey": "GOOD"},
            "awakeCount": {"qualifierKey": "FAIR"},
            "remPercentage": {"value": 19, "qualifierKey": "GOOD"},
            "deepPercentage": {"value": 20, "qualifierKey": "GOOD"},
            "lightPercentage": {"value": 54, "qualifierKey": "GOOD"},
        },
        "sleepVersion": 2,
    },
    "sleepMovement": [],
    "remSleepData": True,
    "sleepLevels": [
        {
            "startGMT": "2026-05-22T05:00:00.0",
            "endGMT": "2026-05-22T05:45:00.0",
            "activityLevel": 2.0,  # light
        },
        {
            "startGMT": "2026-05-22T05:45:00.0",
            "endGMT": "2026-05-22T07:15:00.0",
            "activityLevel": 3.0,  # deep
        },
        {
            "startGMT": "2026-05-22T07:15:00.0",
            "endGMT": "2026-05-22T09:30:00.0",
            "activityLevel": 2.0,  # light
        },
        {
            "startGMT": "2026-05-22T09:30:00.0",
            "endGMT": "2026-05-22T10:54:00.0",
            "activityLevel": 4.0,  # rem
        },
        {
            "startGMT": "2026-05-22T10:54:00.0",
            "endGMT": "2026-05-22T11:24:00.0",
            "activityLevel": 1.0,  # awake
        },
        {
            "startGMT": "2026-05-22T11:24:00.0",
            "endGMT": "2026-05-22T12:24:00.0",
            "activityLevel": 2.0,  # light
        },
    ],
    "restlessMomentsCount": 9,
    "avgOvernightHrv": 58.0,
    "hrvStatus": "BALANCED",
    "bodyBatteryChange": 64,
    "restingHeartRate": 47,
}


# ---------------------------------------------------------------------------
# get_rhr_day(date) — Garmin daily RHR endpoint
# ---------------------------------------------------------------------------
RHR_2026_05_22: dict[str, Any] = {
    "userProfileId": 12345678,
    "statisticsStartDate": "2026-05-22",
    "statisticsEndDate": "2026-05-22",
    "allMetrics": {
        "metricsMap": {
            "WELLNESS_RESTING_HEART_RATE": [
                {
                    "value": 47.0,
                    "calendarDate": "2026-05-22",
                }
            ]
        }
    },
}


# ---------------------------------------------------------------------------
# get_hrv_data(date) — Garmin HRV endpoint
# ---------------------------------------------------------------------------
HRV_2026_05_22: dict[str, Any] = {
    "userProfilePk": 12345678,
    "hrvSummary": {
        "calendarDate": "2026-05-22",
        "weeklyAvg": 56,
        "lastNightAvg": 58,
        "lastNight5MinHigh": 87,
        "baseline": {
            "lowUpper": 41,
            "balancedLow": 41,
            "balancedUpper": 71,
            "markerValue": 0.55,
        },
        "status": "BALANCED",
        "feedbackPhrase": "BALANCED_1",
        "createTimeStamp": "2026-05-22T11:30:11.000",
    },
    "hrvReadings": [
        {
            "hrvValue": 54,
            "readingTimeGMT": "2026-05-22T05:15:00.0",
            "readingTimeLocal": "2026-05-21T22:15:00.0",
        },
        {
            "hrvValue": 59,
            "readingTimeGMT": "2026-05-22T06:30:00.0",
            "readingTimeLocal": "2026-05-21T23:30:00.0",
        },
        {
            "hrvValue": 63,
            "readingTimeGMT": "2026-05-22T08:00:00.0",
            "readingTimeLocal": "2026-05-22T01:00:00.0",
        },
        {
            "hrvValue": 58,
            "readingTimeGMT": "2026-05-22T10:00:00.0",
            "readingTimeLocal": "2026-05-22T03:00:00.0",
        },
    ],
    "startTimestampGMT": "2026-05-22T05:00:00.0",
    "endTimestampGMT": "2026-05-22T12:00:00.0",
    "startTimestampLocal": "2026-05-21T22:00:00.0",
    "endTimestampLocal": "2026-05-22T05:00:00.0",
    "sleepStartTimestampGMT": "2026-05-22T05:00:00.0",
    "sleepEndTimestampGMT": "2026-05-22T12:00:00.0",
}


# ---------------------------------------------------------------------------
# get_training_readiness(date) — Garmin training-readiness endpoint
# ---------------------------------------------------------------------------
TR_2026_05_22: list[dict[str, Any]] = [
    {
        "userProfilePK": 12345678,
        "calendarDate": "2026-05-22",
        "timestamp": "2026-05-22T11:30:00.0",
        "timestampLocal": "2026-05-22T04:30:00.0",
        "deviceId": 9876543210,
        "level": "MODERATE",
        "feedbackLong": "READY_FOR_TRAINING",
        "feedbackShort": "MODERATE",
        "score": 72,
        "sleepScore": 82,
        "sleepScoreFactorPercent": 100,
        "sleepScoreFactorFeedback": "GOOD",
        "recoveryTime": 18,
        "recoveryTimeFactorPercent": 96,
        "recoveryTimeFactorFeedback": "GOOD",
        "acwrFactorPercent": 92,
        "acwrFactorFeedback": "BALANCED",
        "acuteLoad": 412,
        "stressHistoryFactorPercent": 88,
        "stressHistoryFactorFeedback": "BALANCED",
        "hrvFactorPercent": 95,
        "hrvFactorFeedback": "BALANCED",
        "hrvWeeklyAverage": 56,
        "sleepHistoryFactorPercent": 100,
        "sleepHistoryFactorFeedback": "GOOD",
        "validSleep": True,
        "primaryActivityTracker": True,
        "recoveryTimeChangePhrase": None,
    }
]


# ---------------------------------------------------------------------------
# get_max_metrics(date) — Garmin VO2max / fitness-age endpoint
# ---------------------------------------------------------------------------
VO2_2026_05_22: list[dict[str, Any]] = [
    {
        "userId": 12345678,
        "generic": {
            "calendarDate": "2026-05-22",
            "vo2MaxPreciseValue": 56.2,
            "vo2MaxValue": 56,
            "fitnessAge": 32,
            "fitnessAgeDescription": "EXCELLENT",
            "maxMetCategory": 0,
        },
        "cycling": None,
        "heatAltitudeAcclimation": {
            "calendarDate": "2026-05-22",
            "altitudeAcclimationDate": "2026-05-21",
            "previousAltitudeAcclimationDate": "2026-05-18",
            "heatAcclimationDate": "2026-05-20",
            "previousHeatAcclimationDate": "2026-05-15",
            "altitudeAcclimation": 0,
            "previousAltitudeAcclimation": 0,
            "heatAcclimationPercentage": 12,
            "previousHeatAcclimationPercentage": 8,
            "heatTrend": "RECENT_HEAT_GAIN",
            "altitudeTrend": "STABLE",
            "currentAltitude": 124,
            "previousAltitude": 122,
            "acclimationPercentage": 0,
            "previousAcclimationPercentage": 0,
            "altitudeAcclimationLocalTimestamp": "2026-05-21T08:30:00.0",
            "heatAcclimationLocalTimestamp": "2026-05-20T15:00:00.0",
        },
    }
]


# ---------------------------------------------------------------------------
# get_body_battery(start, end) — Garmin body-battery endpoint
# ---------------------------------------------------------------------------
BODY_BATTERY_2026_05_22: list[dict[str, Any]] = [
    {
        "date": "2026-05-22",
        "charged": 64,
        "drained": 51,
        "startTimestampGMT": "2026-05-22T05:00:00.0",
        "endTimestampGMT": "2026-05-22T23:59:00.0",
        "startTimestampLocal": "2026-05-21T22:00:00.0",
        "endTimestampLocal": "2026-05-22T16:59:00.0",
        "bodyBatteryValuesArray": [
            ["2026-05-22T05:00:00.0", 28, "measured", 14.0],
            ["2026-05-22T07:00:00.0", 47, "measured", 14.0],
            ["2026-05-22T09:00:00.0", 89, "measured", 14.0],
            ["2026-05-22T12:00:00.0", 76, "measured", 14.0],
            ["2026-05-22T17:00:00.0", 56, "measured", 14.0],
        ],
        "bodyBatteryDynamicFeedbackEvent": {
            "eventTimestampGmt": "2026-05-22T09:00:00.0",
            "bodyBatteryLevel": "HIGH",
            "feedbackShortType": "RECHARGED",
        },
    }
]


# ---------------------------------------------------------------------------
# get_activities(start, limit) — Garmin activities endpoint
# ---------------------------------------------------------------------------
ACTIVITIES_LAST_10: list[dict[str, Any]] = [
    {
        "activityId": 99001,
        "activityName": "Morning Run",
        "description": None,
        "startTimeLocal": "2026-05-22T06:30:00",
        "startTimeGMT": "2026-05-22T13:30:00",
        "activityType": {
            "typeId": 1,
            "typeKey": "running",
            "parentTypeId": 17,
            "isHidden": False,
            "restricted": False,
            "trimmable": True,
        },
        "eventType": {"typeId": 9, "typeKey": "uncategorized", "sortOrder": 10},
        "comments": None,
        "parentId": None,
        "distance": 8200.0,  # meters
        "duration": 2400.0,  # seconds (40 min)
        "elapsedDuration": 2400.0,
        "movingDuration": 2400.0,
        "elevationGain": 38.0,
        "elevationLoss": 38.0,
        "averageSpeed": 3.417,  # m/s
        "maxSpeed": 4.722,
        "startLatitude": 4.7110,
        "startLongitude": -74.0721,
        "hasPolyline": True,
        "ownerId": 12345678,
        "ownerDisplayName": "broomva",
        "ownerFullName": "Carlos Escobar",
        "ownerProfileImageUrlSmall": None,
        "ownerProfileImageUrlMedium": None,
        "ownerProfileImageUrlLarge": None,
        "calories": 620.0,
        "averageHR": 148.0,
        "maxHR": 171.0,
        "averageRunningCadenceInStepsPerMinute": 168.0,
        "maxRunningCadenceInStepsPerMinute": 188.0,
        "averageBikingCadenceInRevPerMinute": None,
        "maxBikingCadenceInRevPerMinute": None,
        "averageSwimCadenceInStrokesPerMinute": None,
        "maxSwimCadenceInStrokesPerMinute": None,
        "averageSwolf": None,
        "activeLengths": None,
        "steps": 6720,
        "conversationUuid": None,
        "conversationPk": None,
        "numberOfActivityLikes": 0,
        "numberOfActivityComments": 0,
        "likedByUser": False,
        "commentedByUser": False,
        "activityLikeDisplayNames": [],
        "activityLikeFullNames": [],
        "requestorRelationship": None,
        "userRoles": [],
        "privacy": {"typeId": 2, "typeKey": "private"},
        "userPro": False,
        "courseId": None,
        "poolLength": None,
        "unitOfPoolLength": None,
        "hasVideo": False,
        "videoUrl": None,
        "timeZoneId": 144,  # America/Bogota
        "beginTimestamp": 1779449400000,
        "sportTypeId": 1,
        "avgPower": None,
        "maxPower": None,
        "aerobicTrainingEffect": 3.2,
        "anaerobicTrainingEffect": 0.4,
        "strokes": None,
        "normPower": None,
        "leftBalance": None,
        "rightBalance": None,
        "avgLeftBalance": None,
        "max20MinPower": None,
        "avgVerticalOscillation": 8.4,
        "avgGroundContactTime": 248.0,
        "avgStrideLength": 121.0,
        "avgFractionalCadence": 0.5,
        "maxFractionalCadence": 0.0,
        "trainingStressScore": 68.0,
        "intensityFactor": 0.78,
        "vO2MaxValue": 56.2,
        "lapCount": 8,
        "endLatitude": 4.7095,
        "endLongitude": -74.0710,
        "minAirTemperature": 14.0,
        "maxAirTemperature": 19.0,
        "minTemperature": 14.0,
        "maxTemperature": 19.0,
        "deviceId": 9876543210,
        "manufacturer": "GARMIN",
        "lapIndex": 0,
        "locationName": "Bogota",
        "bmrCalories": None,
        "differenceBodyBattery": 8,
        "minActivityLapDuration": 285.0,
        "hasSplits": True,
        "moderateIntensityMinutes": 12,
        "vigorousIntensityMinutes": 28,
        "splitSummaries": [],
        "trainingEffectLabel": "TEMPO",
        "activityTrainingLoad": 132.0,
        "aerobicTrainingEffectMessage": "PRODUCTIVE_TEMPO_4",
        "anaerobicTrainingEffectMessage": "MINOR_ANAEROBIC_BENEFIT_2",
        "splitsCount": 8,
    }
]


# ---------------------------------------------------------------------------
# get_activity(activity_id) — single-activity detail
# ---------------------------------------------------------------------------
ACTIVITY_99001_DETAIL: dict[str, Any] = {
    "activityId": 99001,
    "activityUUID": {"uuid": "abcd1234-ef56-7890-abcd-ef1234567890"},
    "activityName": "Morning Run",
    "summaryDTO": ACTIVITIES_LAST_10[0],
    "metadataDTO": {
        "manufacturer": "GARMIN",
        "deviceMetaDataDTO": {
            "deviceId": 9876543210,
            "deviceTypeId": 1234,
            "deviceVersionId": 5678,
        },
    },
}


# ---------------------------------------------------------------------------
# get_activity_splits(activity_id)
# ---------------------------------------------------------------------------
ACTIVITY_99001_SPLITS: dict[str, Any] = {
    "lapDTOs": [
        {
            "lapIndex": i,
            "startTimeGMT": f"2026-05-22T13:{30 + i * 5}:00.0",
            "distance": 1000.0,
            "duration": 285.0 + i * 2,
            "movingDuration": 285.0,
            "averageHR": 145.0 + i,
            "maxHR": 165.0 + i,
            "averageSpeed": 3.50 - i * 0.02,
            "calories": 75.0,
        }
        for i in range(8)
    ],
    "eventDTOs": [],
}
