from copy import deepcopy
from unittest import TestCase

import numpy as np

import visualiser
from env import Env
from samplers.randomPolicySampler import RandomPolicySampler
from tests.common_vars import template_args
from utils import planner_registry
from utils.common import Node


class TestRandomPolicySampler(TestCase):
    def setUp(self) -> None:

        args = deepcopy(template_args)
        visualiser.VisualiserSwitcher.choose_visualiser("base")

        # setup to use the correct sampler
        args["sampler"] = RandomPolicySampler()

        # use some suitable planner
        args["planner_data_pack"] = planner_registry.PLANNERS["rrt"]

        self.env = Env(args)
        self.sampler = self.env.args.sampler

    def test_init(self):
        # method that does not exists
        with self.assertRaises(ValueError):
            RandomPolicySampler(random_method="foo bar")
        # with supported method
        RandomPolicySampler(random_method="fast")

    def test_get_next_pos(self):
        np.random.seed(0)

        self.sampler.args.goalBias = 0

        # test all results are different
        results = set()
        for i in range(100):
            results.add(Node(self.sampler.get_next_pos()[0]))
        self.assertEqual(len(results), 100)

        self.sampler.args.goalBias = 1

        # test all results, because of goalBias, are same
        results = set()
        for i in range(100):
            results.add(Node(self.sampler.get_next_pos()[0]))
        self.assertEqual(len(results), 1)

        # test that the result is the exact same point as the goal point
        self.assertEqual(results.pop(), self.sampler.args.goal_pt)
