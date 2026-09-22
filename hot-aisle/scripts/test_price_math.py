import unittest
from price_math import allocation_cost, required_throughput_ratio, cost_per_1000, relative_unit_cost_reduction

class PriceMathTests(unittest.TestCase):
    def test_h100_october_threshold(self):
        self.assertAlmostEqual(required_throughput_ratio(2.99,4.50),0.6644444444444445)
    def test_h200_october_threshold(self):
        self.assertAlmostEqual(required_throughput_ratio(2.99,5.40),0.5537037037037037)
    def test_b200_october_threshold(self):
        self.assertAlmostEqual(required_throughput_ratio(2.99,8.50),0.3517647058823529)
    def test_current_h100_differs(self):
        self.assertAlmostEqual(required_throughput_ratio(2.99,3.85),0.7766233766233767)
    def test_lower_priced_competitor(self):
        self.assertGreater(required_throughput_ratio(2.99,1.80),1)
    def test_all_eight_bare_metal_gpus_count(self):
        self.assertAlmostEqual(allocation_cost(3.39,8),27.12)
    def test_extras_count(self):
        self.assertAlmostEqual(allocation_cost(2.99,2,1),6.98)
    def test_cost_per_1000(self):
        self.assertAlmostEqual(cost_per_1000(3.6,1),1)
    def test_tie_at_break_even(self):
        self.assertAlmostEqual(cost_per_1000(2.99,2.99/4.5),cost_per_1000(4.5,1))
    def test_negative_savings_are_retained(self):
        self.assertLess(relative_unit_cost_reduction(2,1),0)
    def test_invalid_rates_fail(self):
        for value in [0,-1,float('nan'),float('inf'),True,'1']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                cost_per_1000(2.99,value)
    def test_invalid_gpu_counts_fail(self):
        for value in [0,-1,1.5,True,'8']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                allocation_cost(2.99,value)
    def test_zero_comparator_cost_fails(self):
        with self.assertRaises(ValueError):
            required_throughput_ratio(2.99,0)

if __name__ == '__main__':
    unittest.main()
