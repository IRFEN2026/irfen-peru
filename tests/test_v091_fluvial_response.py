"""Research-only lag protocol regression tests; no external data nor invented observed flows."""
import unittest
from datetime import date, timedelta
from scripts import v091_fluvial_response as F


class FluvialLagQA(unittest.TestCase):
    def test_tied_rank(self):
        self.assertEqual(F.rank([2, 4, 2, 9]), [1.5, 3.0, 1.5, 4.0])

    def test_constant_series_has_no_fabricated_correlation(self):
        self.assertIsNone(F.spearman([0,0,0], [1,2,3]))

    def test_missing_day_in_window_is_unknown_not_zero(self):
        rain = {date(2020,1,1): 8., date(2020,1,3): 6.}
        self.assertIsNone(F.accum_at(rain,date(2020,1,3),3))
        self.assertEqual(F.accum_at(rain,date(2020,1,3),1),6.)

    def test_no_future_rain_leakage(self):
        d = date(2021,2,8)
        rain={d-timedelta(days=i):float(i+1) for i in range(6)}
        rain[d+timedelta(days=1)]=9000.
        flow={d:14.}
        p,q,dates=F.paired(rain,flow,3,1,F.PERIODS["holdout"])
        self.assertEqual(p,[2.+3.+4.])
        self.assertEqual(q,[14.])
        self.assertEqual(dates,[d.isoformat()])

    def test_holdout_does_not_choose_train_lag(self):
        rain={}
        flow={}
        origin=date(2016,1,1)
        for i in range(240):
            d=origin+timedelta(days=i)
            rain[d]=float(i%13)
            flow[d]=float((i-2)%13)
        out=F.evaluate_pair(rain,flow,min_pairs=40)
        self.assertIsNotNone(out["selected_on_train"])
        self.assertEqual(out["holdout"]["status"],"INSUFFICIENT_HOLDOUT_PAIRS")

    def test_monthly_anomaly_excludes_groups_with_fewer_than_four_observations(self):
        x=[1,3,5,7,9,11]
        y=[11,9,7,5,3,1]
        dates=["2021-01-01","2021-01-02","2021-01-03",
               "2021-02-01","2021-02-02","2021-02-03"]
        self.assertEqual(F.monthly_anomaly_spearman(x,y,dates,minimum=2)["status"],
                         "INSUFFICIENT_WITHIN_MONTH")

    def test_future_rain_is_explicitly_noncausal_control(self):
        day=date(2022,2,1)
        rain={day+timedelta(days=i):float(i) for i in range(1,10)}
        flows={day:5.}
        d=F.future_rain_falsification(rain,flows,3,(2021,2023),minimum=5)
        self.assertIsNone(d["spearman"])
        self.assertEqual(d["interpretation"],"FUTURE_RAIN_NEGATIVE_CONTROL_NOT_PREDICTIVE")

    def test_documentary_gauge_identity_blocks_unlabeled_months(self):
        doc={"months":[{"month":"2017-03","tables":{"rivers":{
            "column_identity_from_report_notes":{},
            "days":{"1":{"readers":"DOS_LECTORES","values":{"R_PIURA_1":300}}}}}}]}
        flow,_=F.flow_series(doc,"R_PIURA_1","PUENTE_SANCHEZ_CERRO")
        self.assertEqual(flow,{})

    def test_only_double_reader_nonnegative_flow(self):
        doc={"months":[{"month":"2017-03","tables":{"rivers":{"days":{
            "1":{"readers":"DOS_LECTORES","values":{"EL_CIRUELO":10}},
            "2":{"readers":"UN_LECTOR","values":{"EL_CIRUELO":12}},
            "3":{"readers":"DOS_LECTORES","values":{"EL_CIRUELO":-1}}}}}}]}
        flow,excluded=F.flow_series(doc,"EL_CIRUELO")
        self.assertEqual(len(flow),1)
        self.assertEqual(excluded,2)

    def test_no_claim_of_predictive_skill(self):
        from unittest.mock import patch
        with patch.object(F, "PECHP") as p:
            # Schema/guards can be reviewed without running full archive in this unit test.
            self.assertFalse(F.PAIRS[0].get("public_alerting",False))
            self.assertTrue(all(p["river"]!="Tumbes" for p in F.PAIRS))

if __name__=="__main__":
    unittest.main()
