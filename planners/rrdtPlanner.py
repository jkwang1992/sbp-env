import logging
import random
import matplotlib.pyplot as plt
import math

import numpy as np
from scipy.special import i0

from overrides import overrides
from tqdm import tqdm

from planners.randomPolicySampler import RandomPolicySampler
from planners.baseSampler import Sampler
from planners.rrtPlanner import RRTPlanner
from randomness import NormalRandomnessManager
from helpers import BFS, update_progress

LOGGER = logging.getLogger(__name__)

MAX_NUMBER_NODES = 20000

randomnessManager = NormalRandomnessManager()

ENERGY_MIN = 0
ENERGY_MAX = 10
ENERGY_COLLISION_LOSS = 1

RESAMPLE_RESTART_EVERY = 0 # 200
RANDOM_RESTART_EVERY = 20
ENERGY_START = 10
RANDOM_RESTART_PARTICLES_ENERGY_UNDER = 0.1#.75



class DisjointTreeParticle:

    def __init__(self,
                 planner,
                 p_manager,
                 direction=None,
                 pos=None,
                 isroot=False,
                 startPtNode=None):
        self.isroot = isroot
        self.p_manager = p_manager
        self.planner = planner
        self.last_node = None

        self.restart(direction=direction, pos=pos, restart_when_merge=False)

    def _restart(self, direction=None, pos=None):
        if direction is None:
            # I will generate one if you dont give me!
            direction = random.uniform(0, math.pi * 2)
        if pos is None:
            # I cant really get started...can i?
            raise Exception("No pos given")
        # self.energy = 1
        self.dir = direction
        self.pos = np.copy(pos)

        self._trying_this_pos = np.copy(pos)
        self.provision_dir = None
        self.successed = 0
        self.failed = 0
        self.failed_reset = 0

    def restart(self, direction=None, pos=None, restart_when_merge=True):
        if self.isroot:
            # root particles has a different initialisation method
            # (for the first time)
            self.isroot = False
            self._restart(direction, pos)
            return
        self.last_node = None
        merged_tree = None
        try:
            if len(self.tree.nodes) < 5:
                # don't bother!
                try:
                    self.p_manager.args.planner.disjointedTrees.remove(self.tree)
                except ValueError:
                    pass
            # print(len(self.tree.nodes))
        except AttributeError:
            # probably this is its first init
            pass
        if pos is None:
            # get random position
            pos = self.p_manager.new_pos_in_free_space()
            merged_tree = self.planner.add_pos_to_existing_tree(
                Node(pos), None)
            if merged_tree is not None and restart_when_merge:
                # Successfully found a new valid node that's close to existing tree
                # Return False to indicate it (and abort restart if we want more exploration)
                self.p_manager.add_to_restart(self)
                # we need to abort the restart procedure. add this to pending restart
                return False
        try:
            self.tree.particle_handler.remove(self)
        except AttributeError:
            # probably this is its first init
            pass
        # initialise to initial value, create new d-tree
        if merged_tree is not None:
            self.tree = merged_tree
            merged_tree.particle_handler.append(self)
        else:
            # spawn a new tree
            self.tree = TreeDisjoint(particle_handler=self, dim=self.p_manager.args.num_dim)
            self.tree.add_newnode(Node(pos))
            self.planner.disjointedTrees.append(self.tree)
        self.p_manager.modify_energy(particle_ref=self, set_val=ENERGY_START)
        self._restart(direction, pos)
        return True

    def try_new_pos(self, new_pos, new_dir):
        # pos is a 2 index list-type object
        # Do nothing with new_pos for now as we confirm our final location via callback
        #################################################################################
        # new_dir is a scalar (for now TODO make it to general dimension later)
        self.provision_dir = new_dir

    def confirm(self, pos):
        # to confirm the final location of newly added tree node
        self.pos = pos
        self.dir = self.provision_dir


class DynamicDisjointTreeParticle(DisjointTreeParticle):
    def __init__(self, proposal_type, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.last_failed = False

        if proposal_type not in ('dynamic-vonmises', 'ray-casting', 'original'):
            raise Exception("Given proposal type is not supported.")
        self.proposal_type = proposal_type
        # self.proposal_type = 'dynamic-vonmises'
        # self.proposal_type = 'ray-casting'
        # self.proposal_type = 'original'

        self.show_fig = True
        self.show_fig = False

        self.kappa = np.pi * 1.5

        mu = 0
        self.successed = 0
        self.failed = 0
        self.failed_reset = 0

        if self.proposal_type in ('dynamic-vonmises', 'ray-casting', 'original'):
            self.last_origin = None
            # x = np.linspace(-np.pi, np.pi, num=61)
            # y = np.exp(self.kappa*np.cos(x-mu))/(2*np.pi*i0(self.kappa))
            # self.x = x
            # self.y = y / np.linalg.norm(y, ord=1)

            pass
            self.A = None
            # random mu
            # mu = np.random.rand(3)
            # mu = mu / np.linalg.norm(mu, ord=1)
            # self.x, self.y = self.generate_pmf(dim=6, mu=mu, kappa=2)
            #
            # self.A = self.y.copy()
            # self.last_origin = mu

        ############################################## https://stackoverflow.com/questions/4098131/how-to-update-a-plot-in-matplotlib
            if self.show_fig:
                self.fig = plt.figure()
                self.ax = self.fig.add_subplot(111)
                self.line1, = self.ax.plot(x, y, 'r-') # Returns a tuple of line objects, thus the comma

                # for phase in self.x:
                plt.draw()
                plt.pause(1e-4)

    @staticmethod
    def rand_unit_vecs(num_dims, number):
        """Get random unit vectors"""
        vec = np.random.standard_normal((number, num_dims))
        vec = vec / np.linalg.norm(vec, axis=1)[:, None]
        return vec

    @staticmethod
    def generate_pmf(num_dims, mu, kappa, unit_vector_support=None, num=None, plot=False):
        assert num_dims >= 1
        if num is None:
            num = 361 * (num_dims - 1) ** 2
        # assert np.all(np.isclose(np.linalg.norm(mu, axis=0), 1)), mu
        ####
        if unit_vector_support is None:
            unit_vector_support = DynamicDisjointTreeParticle.rand_unit_vecs(num_dims,
                                                                             num).T

        pmf = np.exp(kappa * mu.dot(unit_vector_support))
        pmf = pmf / pmf.sum()

        return unit_vector_support, pmf

    def draw_sample(self, origin=None):
        if self.proposal_type in ('dynamic-vonmises', 'original'):

            if self.last_origin is None:
                # first time
                mu = np.random.standard_normal((1, self.p_manager.args.num_dim))
                mu = mu / np.linalg.norm(mu, axis=1)[:, None]
                self.provision_dir = mu[0]
                return self.provision_dir
            elif self.A is None:
                self.x, self.y = self.generate_pmf(num_dims=self.p_manager.args.num_dim, mu=self.last_origin, kappa=2)

                self.A = self.y.copy()
                # self.last_origin = mu

        if origin is None:
            # use self direction if none is given.
            origin = self.dir

        # self.last_origin = origin

        # use argmax or draw probabilistically
        if self.proposal_type == 'ray-casting':
            if not self.last_failed:
                # skip drawing if we haven't failed (if we are using ray-casting)
                # this should return the origin of where we came from
                return origin
            x_idx = y_idx = np.argmax(self.A)
            xi = self.x[x_idx]

        elif self.proposal_type == 'dynamic-vonmises':
            # bin_width = self.x[1] - self.x[0]
            xi_idx = np.random.choice(range(self.x.shape[1]), p=self.A)
            xi = self.x[:, xi_idx]
            # xi = np.random.uniform(xi, xi + bin_width)

        elif self.proposal_type == 'original':
            # bin_width = self.x[1] - self.x[0]
            xi_idx = np.random.choice(range(self.x.shape[1]), p=self.A)
            xi = self.x[:, xi_idx]
            # xi = np.random.uniform(xi, xi + bin_width)
            # global randomnessManager
            # xi = randomnessManager.draw_normal(origin=origin, kappa=self.kappa)

        else:
            raise Exception("BUGS?")
        return xi #+ origin

    def success(self):
        self.successed += 1
        self.failed_reset = 0
        self.last_origin = self.provision_dir
        if self.proposal_type in ('dynamic-vonmises', 'ray-casting', 'original'):
            # reset to the original von mises
            # TODO make a sharper von mises distribution (higher kappa) when succes
            # self.A = self.y.copy()
            self.A = None

            self.last_failed = False

            if self.show_fig:

                self.ax.clear()
                self.ax.set_xlim([-4,4])
                self.ax.set_ylim([0, .1])
                # self.reset_vonmises()
                self.line1, = self.ax.plot(self.x, self.y, 'r-') # Returns a tuple of line objects, thus the comma
                plt.draw()
                plt.pause(1e-4)

    def fail(self):
        self.failed_reset += 1
        self.failed += 1
        if self.proposal_type in ('dynamic-vonmises', 'ray-casting'):
            if self.last_origin is None:
                # still in phrase 1
                return
            self.last_failed = True
            def k(x, xprime, sigma=.1, length_scale=np.pi / 4):
                return sigma**2 * np.exp(-(2 *np.sin((x - xprime)/2)**2)/ (length_scale**2))

            def k(x, xprime, sigma=.1, length_scale=np.pi / 4):
                return sigma ** 2 * np.exp(-(2 * np.sin(
                    (np.linalg.norm(x - xprime[:, None], axis=0)) / 2) ** 2) / (
                                                       length_scale ** 2))

            # get previous trying direction
            xi = self.provision_dir

            # revert effect of shifting origin
            xi -= self.last_origin

            # find cloest x idx
            # x_idx = np.abs(self.x - xi).argmin() # <---- FIXME this is dumb. store the x_idx used when we do the sampling to save computational time
            #
            # y_val = self.y[x_idx]
            self.A = self.A - k(self.x, xi, sigma=np.sqrt(self.A)*.9, length_scale=np.pi/10)
            self.A = self.A / np.linalg.norm(self.A, ord=1)

            if self.show_fig:
                self.ax.plot(self.x, self.y)
                self.ax.plot([xi, xi], [0, .05], 'r-', lw=2)

                self.line1.set_ydata(self.A)
                self.fig.canvas.draw()
                self.fig.canvas.flush_events()

                plt.draw()
                plt.pause(1e-4)



class RRdTSampler(Sampler):

    def __init__(self, restart_when_merge=True):
        self.restart_when_merge = restart_when_merge
        self._last_prob = None

        self._c_random = 0
        self.last_choice = 0
        self.last_failed = True


    def init(self, **kwargs):
        super().init(**kwargs)
        # For benchmark stats tracking
        self.args.env.stats.lscampler_restart_counter = 0
        self.args.env.stats.lscampler_randomwalk_counter = 0

        self.randomSampler = RandomPolicySampler()
        self.randomSampler.init(**kwargs)

        self.p_manager = MABScheduler(num_dtrees=4,
                                      startPt=self.start_pos,
                                      goalPt=self.goal_pos,
                                      args=self.args)

        self.p_manager.randomSampler = self.randomSampler

        global MAX_NUMBER_NODES
        MAX_NUMBER_NODES = self.args.max_number_nodes

        for _ in range(self.p_manager.num_dtrees - 2):  # minus two for start and goal point
            pos = self.p_manager.new_pos_in_free_space()

            dt_p = DynamicDisjointTreeParticle(
                proposal_type=self.args.rrdt_proposal_distribution,
                direction=random.uniform(0, math.pi * 2),
                planner=self.args.planner,
                pos=pos,
                p_manager=self.p_manager,
            )

            self.p_manager.particles.append(dt_p)
        # spawn one that comes from the root
        root_particle = DynamicDisjointTreeParticle(
            proposal_type=self.args.rrdt_proposal_distribution,
            direction=random.uniform(0, math.pi * 2),
            planner=self.args.planner,
            pos=self.start_pos,
            isroot=True,
            p_manager=self.p_manager,
            )
        # spawn one that comes from the goal
        goal_dt_p = DynamicDisjointTreeParticle(
            proposal_type=self.args.rrdt_proposal_distribution,
            direction=random.uniform(0, math.pi * 2),
            planner=self.args.planner,
            pos=self.goal_pos,
            isroot=False,
            p_manager=self.p_manager,
            )
        # goal_dt_p.restart(
        #             restart_when_merge=self.restart_when_merge)
        # goal_dt_p.restart(
        #             restart_when_merge=False)

        goal_dt_p.tree.add_newnode(self.args.env.goalPt)
        self.p_manager.particles.append(goal_dt_p)
        #
        self.args.planner.root = TreeRoot(
            particle_handler=root_particle,
            dim=self.args.num_dim
        )
        root_particle.tree = self.args.planner.root
        root_particle.tree.add_newnode(self.args.env.startPt)
        #
        self.p_manager.particles.append(root_particle)

    def particles_random_free_space_restart(self):
        for i in range(self.p_manager.num_dtrees):
            if self.p_manager.dtrees_energy[
                    i] < RANDOM_RESTART_PARTICLES_ENERGY_UNDER:
                self.p_manager.add_to_restart(self.p_manager.particles[i])
                # _z = self.p_manager.particles[i]
                # print(_z.successed, _z.failed, _z.failed_reset)


    def report_success(self, idx, **kwargs):
        self.p_manager.particles[idx].last_node = kwargs['newnode']
        self.p_manager.confirm(idx, kwargs['pos'])
        self.last_failed = False

        self.p_manager.particles[idx].success()
        # if self.p_manager.particles[0].proposal_type != 'ray-casting':
        # self.p_manager.modify_energy(idx=idx, factor=1-1e-9)
        # self.p_manager.modify_energy(idx=idx, factor=.99)

    def report_fail(self, idx, **kwargs):
        self.last_failed = True
        if idx >= 0:
            self.p_manager.modify_energy(idx=idx, factor=0.7)
            self.p_manager.particles[idx].fail()

    def restart_all_pending_local_samplers(self):
        # restart all pending local samplers
        while len(self.p_manager.local_samplers_to_be_rstart) > 0:
            # during the proces of restart, if the new restart position
            # is close to an existing tree, it will simply add to that new tree.
            if not self.p_manager.local_samplers_to_be_rstart[0].restart(
                    restart_when_merge=self.restart_when_merge):
                # This flag denotes that a new position was found among the trees,
                # And it NEEDS to get back to restarting particles in the next ierations
                return False
            self.p_manager.local_samplers_to_be_rstart.pop(0)
            return True
        return True

    def get_next_pos(self):
        self._c_random += 1

        if self._c_random > RANDOM_RESTART_EVERY > 0:
            self._c_random = 0
            self.particles_random_free_space_restart()
        if not self.restart_all_pending_local_samplers():
            LOGGER.debug("Adding node to existing trees.")
            return None
        # get a node to random walk
        choice = self.get_random_choice()

        # NOTE This controls if testing (via mouse) or actual runs
        pos = self.randomWalk(choice)
        # pos, choice = self.random_walk_by_mouse()
        return (pos, self.p_manager.particles[choice].tree,
                self.p_manager.particles[choice].last_node,
                lambda c=choice, **kwargs: self.report_success(c, **kwargs),
                lambda c=choice, **kwargs: self.report_fail(c, **kwargs))

    def random_walk_by_mouse(self):
        """FOR testing purpose. Mimic random walk, but do so via mouse click."""
        from planners.mouseSampler import MouseSampler as mouse
        pos = mouse.get_mouse_click_position(scaling=self.scaling)
        # find the cloest particle from this position
        _dist = None
        p_idx = None
        for i in range(len(self.p_manager.particles)):
            p = self.p_manager.particles[i]
            if _dist is None or _dist > self.args.env.dist(pos, p.pos):
                _dist = self.args.env.dist(pos, p.pos)
                p_idx = i
        LOGGER.debug("num of tree: {}".format(
            len(self.disjointedTrees)))
        self.p_manager.new_pos(idx=p_idx, pos=pos, dir=0)
        return pos, p_idx

    def randomWalk(self, idx):
        self.args.env.stats.lscampler_randomwalk_counter +=1
        # Randomly bias toward goal direction
        if False and random.random() < self.args.goalBias:
            dx = self.goal_pos[0] - self.p_manager.get_pos(idx)[0]
            dy = self.goal_pos[1] - self.p_manager.get_pos(idx)[1]
            goal_direction = math.atan2(dy, dx)
            # new_direction = self.randomnessManager.draw_normal(origin=goal_direction, kappa=1.5)
            new_direction = self.p_manager.particles[idx].draw_sample(origin=goal_direction)
        else:
            # new_direction = self.randomnessManager.draw_normal(origin=self.p_manager.get_dir(idx), kappa=1.5)
            new_direction = self.p_manager.particles[idx].draw_sample()

        # print(new_direction)
        # unit_vector = np.array([math.cos(new_direction), math.sin(new_direction)])
        new_pos = self.p_manager.get_pos(idx) + new_direction * self.args.epsilon * 3
        self.p_manager.new_pos(idx=idx,
                               pos=new_pos,
                               dir=new_direction)
        return new_pos

    def get_random_choice(self):
        if self.p_manager.num_dtrees == 1:
            return 0
        if self.args.keep_go_forth:
            # check if we can skip the rest in ray-casting method by priortising straight line
            if self.p_manager.particles[0].proposal_type == 'ray-casting' and not self.last_failed:
                return self.last_choice

        prob = self.p_manager.get_prob()
        self._last_prob = prob  # this will be used to paint particles
        try:
            choice = np.random.choice(range(self.p_manager.num_dtrees), p=prob)
        except ValueError as e:
            # NOTE dont know why the probability got out of sync... We notify the use, then try re-sync the prob
            LOGGER.error("!! probability got exception '{}'... trying to re-sync prob again.".format(e))
            self.p_manager.resync_prob()
            prob = self.p_manager.get_prob()
            self._last_prob = prob
            choice = np.random.choice(range(self.p_manager.num_dtrees), p=prob)
        self.last_choice = choice
        return choice



############################################################
##    PATCHING RRT with disjointed-tree specific stuff    ##
############################################################


class Node:
    def __init__(self, pos):
        self.pos = np.array(pos)
        self.cost = 0  # index 0 is x, index 1 is y
        self.edges = []
        self.children = []
        self.is_start = False
        self.is_goal = False

    def __repr__(self):
        try:
            num_edges = len(self.edges)
        except AttributeError:
            num_edges = "DELETED"
        return "Node(pos={}, cost={}, num_edges={})".format(
            self.pos, self.cost, num_edges)


class RRdTPlanner(RRTPlanner):

    def __init__(self, *argv, **kwargs):
        super().__init__(*argv, **kwargs)
        self.root = None
        self.disjointedTrees = []

    @overrides
    def run_once(self):
        # Get an sample that is free (not in blocked space)
        # _tmp = self.args.sampler.get_valid_next_pos()
        # print(self.args.goal_radius)

        while True:
            _tmp = self.args.sampler.get_next_pos()
            if _tmp is None:
                # This denotes a particle had tried to restart and added the new node
                # to existing tree instead. Skip remaining steps and iterate to next loop
                _tmp = None
                break
            rand_pos = _tmp[0]
            self.args.env.stats.add_sampled_node(rand_pos)
            if self.args.env.cc.feasible(rand_pos):
                pass
                self.args.env.stats.sampler_success += 1
                break
            report_fail = _tmp[-1]
            report_fail(pos=rand_pos, obstacle=True)
            self.args.env.stats.add_invalid(obs=True)
            self.args.env.stats.sampler_fail += 1

        self.args.env.stats.sampler_success_all += 1

        if _tmp is None:
            # we have added a new samples when respawning a local sampler
            return
        rand_pos, parent_tree, last_node, report_success, report_fail = _tmp
        if last_node is not None and False:
            # use the last succesful node as the nearest node
            # This is expliting the advantage of local sampler :)
            nn = last_node
            newpos = rand_pos
        else:
            idx = self.find_nearest_neighbour_idx(
                rand_pos, parent_tree.poses[:len(parent_tree.nodes)])
            nn = parent_tree.nodes[idx]
            # get an intermediate node according to step-size
            newpos = self.args.env.step_from_to(nn.pos, rand_pos)
        # check if it is free or not
        if not self.args.env.cc.visible(nn.pos, newpos):
            self.args.env.stats.add_invalid(obs=False)
            report_fail(pos=rand_pos, free=False)
        else:
            newnode = Node(newpos)

            # if True:
            #     from klampt import vis
            #     from klampt.model.coordinates import Point, Direction
            #     import numpy as np
            #
            #     self.args.env.cc.robot.setConfig(self.args.env.cc._translate_to_klampt(newpos))
            #     link = self.args.env.cc.robot.link(11)
            #
            #     unique_label = f"pt{self.args.env.stats.valid_sample}"
            #     pos = link.getWorldPosition([0, 0, 0])
            #     vis.add(unique_label, Point(pos), keepAppearance=True)
            #     # print(unique_label)
            #     vis.setAttribute(unique_label, "size", 20)
            #     vis.setAttribute(unique_label, "color", (1, 0, 0, 1))
            #     vis.hideLabel(unique_label)


            self.args.env.stats.add_free()
            self.args.sampler.add_tree_node(newnode.pos)
            report_success(newnode=newnode, pos=newnode.pos)
            ######################
            newnode, nn = self.connect_two_nodes(
                newnode, nn, parent_tree)
            # try to add this newnode to existing trees
            self.add_pos_to_existing_tree(
                newnode, parent_tree)

    def rrt_star_add_node(self, newnode, nn=None):
        """This function perform finding optimal parent, and rewiring."""

        newnode, nn = self.choose_least_cost_parent(
            newnode, nn=nn, nodes=self.root.nodes)
        self.rewire(newnode, nodes=self.root.nodes)

        # newnode.parent = nn

        # check for goal condition
        if self.args.env.dist(newnode.pos, self.goalPt.pos) < self.args.goal_radius:
            if self.args.env.cc.visible(newnode.pos, self.goalPt.pos):
                if newnode.cost < self.c_max:
                    self.c_max = newnode.cost
                    self.goalPt.parent = newnode
                    newnode.children.append(self.goalPt.parent)
        return newnode, nn

##################################################
## Tree management:
##################################################
    def connect_two_nodes(self, newnode, nn, parent_tree=None):
        """Add node to disjoint tree OR root tree."""

        # # hot fix. if nn has no edges, it should be from root tree
        # if parent_tree is not self.root:
        #     try:
        #         nn.edges
        #         newnode.edges
        #     except AttributeError:
        #         parent_tree = self.root
        #         LOGGER.warning(
        #             f"HOT FIX with parent_tree-is-None={parent_tree is None}"
        #         )

        if parent_tree is self.root:
            # using rrt* algorithm to add each nodes
            newnode, nn = self.rrt_star_add_node(newnode, nn)
        else:
            newnode.edges.append(nn)
            nn.edges.append(newnode)
        if parent_tree is not None:
            parent_tree.add_newnode(newnode)
        return newnode, nn

    def add_pos_to_existing_tree(self, newnode, parent_tree):
        """Try to add pos to existing tree. If success, return True."""
        r = self.args.epsilon
        if self.args.engine == 'klampt':
            r = 1
        nearest_nodes = self.find_nearest_node_from_neighbour(
            node=newnode, parent_tree=parent_tree, radius=r)
        cnt = 0
        for nearest_neighbour_node, nearest_neighbour_tree in nearest_nodes:
            cnt += 1
            if cnt > 5:
                break
        # for nearest_neighbour_node, nearest_neighbour_tree in nearest_nodes:
            if self.args.env.cc.visible(newnode.pos,
                                        nearest_neighbour_node.pos):
                if parent_tree is None:
                    ### joining ORPHAN NODE to a tree
                    self.connect_two_nodes(newnode, nearest_neighbour_node,
                                           nearest_neighbour_tree)
                    parent_tree = nearest_neighbour_tree
                    # LOGGER.debug(
                    #     " ==> During respawning particle, joining to existing tree with size: {}"
                    #     .format(len(nearest_neighbour_tree.nodes)))
                else:
                    ### joining a TREE to another tree
                    try:
                        parent_tree = self.join_trees(
                            parent_tree,
                            nearest_neighbour_tree,
                            tree1_node=newnode,
                            tree2_node=nearest_neighbour_node)
                        return parent_tree
                    except AssertionError as e:
                        LOGGER.warning(
                            "== Assertion error in joining sampled point to existing tree... Skipping this node..."
                        )
                break
        return parent_tree

    def find_nearest_node_from_neighbour(self, node, parent_tree, radius):
        """
        Given a tree, a node within that tree, and radius
        Return a list of cloest nodes (and its corresponding tree) within the radius (that's from other neighbourhood trees)
        Return None if none exists
        IF root exists in the list, add it at the last position (So the connection behaviour would remain stable)
            This ensure all previous action would only add add edges to each nodes, and only the last action would it
            modifies the entire tree structures wtih rrt* procedures.
        """
        nearest_nodes = {}
        for tree in [*self.disjointedTrees, self.root]:
            if tree is parent_tree:
                # skip self
                continue
            idx = self.find_nearest_neighbour_idx(
                node.pos, tree.poses[:len(tree.nodes)])
            nn = tree.nodes[idx]
            if self.args.env.dist(nn.pos, node.pos) < radius:
                nearest_nodes[tree] = nn
        # construct list of the found solution. And root at last (or else the result won't be stable)
        root_nn = nearest_nodes.pop(self.root, None)
        nearest_nodes_list = [(nearest_nodes[key], key)
                              for key in nearest_nodes]
        if root_nn is not None:
            nearest_nodes_list.append((root_nn, self.root))
        return nearest_nodes_list

    def join_tree_to_root(self, tree, middle_node, root_tree_node):
        """It will join the given tree to the root"""
        # from env import Colour
        bfs = BFS(middle_node, validNodes=tree.nodes)
        # add all nodes from disjoint tree via rrt star method
        LOGGER.info("> Joining to root tree")
        with tqdm(desc="join to root", total=len(tree.nodes)) as pbar:

            # if not self.args.env.cc.visible(middle_node.pos, root_tree_node.pos):
            #     xxxxxxxxxxxxxxxxxX
            nn = middle_node
            # while bfs.has_next():
            #     n = bfs.next()
            #     if not self.args.env.cc.visible(nn.pos, n.pos):
            #         xxxxxxxxxxxxxxxxxX
            #     nn = n


            bfs = BFS(middle_node, validNodes=tree.nodes)
            nn = root_tree_node
            while bfs.has_next():
                newnode = bfs.next()
                pbar.update()
                try:
                    # self.connect_two_nodes(newnode, nn=None, parent_tree=self.root)
                    # if not self.args.env.cc.visible(newnode.pos, nn.pos):
                    #     asdasd
                    # newnode, nn = self.connect_two_nodes(newnode, nn=nn, parent_tree=self.root)
                    newnode, nn = self.connect_two_nodes(newnode, nn=None, parent_tree=self.root)
                    nn = newnode
                except LookupError:
                    LOGGER.warning(
                        "nn not found when attempting to joint to root. Ignoring..."
                    )
                # remove this node's edges (as we don't have a use on them anymore) to free memory
                del newnode.edges

        # assert progress == total_num, "Inconsistency in BFS walk {} != {}".format(
        #     progress, total_num)


    def join_trees(self, tree1, tree2, tree1_node, tree2_node):
        """
        Join the two given tree together (along with their nodes).
        It will delete the particle reference from the second tree.
        It will use RRT* method to add all nodes if one of the tree is the ROOT.

        tree1_node & 2 represent the nodes that join the two tree together. It only matters currently to
        joining root tree to disjointed treeself.

        Return the tree that has not been killed
        """
        assert tree1 is not tree2, "Both given tree should not be the same"
        # try:
        #     tree1.nodes
        #     tree2.nodes
        # except:
        #     return
        if tree1 is self.root:
            assert tree1 not in self.disjointedTrees, "Given tree is neither in disjointed tree, nor is it the root: {}".format(
                tree1)
        elif tree2 is self.root:
            assert tree2 not in self.disjointedTrees, "Given tree is neither in disjointed tree, nor is it the root: {}".format(
                tree2)

        LOGGER.info(" => Joining trees with size {} to {}".format(
            len(tree1.nodes), len(tree2.nodes)))
        # Re-arrange only. Make it so that tree1 will always be root (if root exists among the two)
        # And tree1 node must always be belong to tree1, tree2 node belong to tree2
        if tree1 is not self.root:
            # set tree1 as root (if root exists among the two)
            tree1, tree2 = tree2, tree1
        if tree1_node in tree2.nodes or tree2_node in tree1.nodes:
            # swap to correct position
            tree1_node, tree2_node = tree2_node, tree1_node
        # assert tree1_node in tree1.nodes, "Given nodes does not belong to the two given corresponding trees"
        # assert tree2_node in tree2.nodes, "Given nodes does not belong to the two given corresponding trees"

        if tree1 is self.root:
            # find which middle_node belongs to the disjointed tree
            self.join_tree_to_root(tree2, tree2_node, root_tree_node=tree1_node)
            # self.connect_two_nodes(tree1_node, tree2_node, draw_only=True)
        else:
            self.connect_two_nodes(tree1_node, tree2_node)
            tree1.extend_tree(tree2)
        del tree2.nodes
        del tree2.poses
        self.disjointedTrees.remove(tree2)

        if self.args.sampler.restart_when_merge:
            # restart all particles
            for p in tree2.particle_handler:
                p.restart()
            del tree2.particle_handler
        else:
            # pass the remaining particle to the remaining tree
            for p in tree2.particle_handler:
                p.tree = tree1
                tree1.particle_handler.append(p)
        return tree1


############################################################
##                         Classes                        ##
############################################################


class TreeRoot:
    def __init__(self, particle_handler, dim):
        self.particle_handler = [particle_handler]
        self.nodes = []
        self.poses = np.empty((MAX_NUMBER_NODES*2 + 50,
                               dim))  # +50 to prevent over flow
        # This stores the last node added to this tree (by local sampler)

    def add_newnode(self, node):
        self.poses[len(self.nodes)] = node.pos
        self.nodes.append(node)

    def extend_tree(self, tree):
        self.poses[len(self.nodes):len(self.nodes) +
                   len(tree.nodes)] = tree.poses[:len(tree.nodes)]
        self.nodes.extend(tree.nodes)

    def __repr__(self):
        string = super().__repr__()
        string += '\n'
        import pprint
        string += pprint.pformat(vars(self), indent=4)
        # string += ', '.join("%s: %s" % item for item in vars(self).items())
        return string


class TreeDisjoint(TreeRoot):
    @overrides
    def __init__(self, **kwargs):
        super().__init__(**kwargs)



class MABScheduler:
    def __init__(self, num_dtrees, startPt, goalPt, args):
        self.num_dtrees = num_dtrees
        self.init_energy()
        self.particles = []
        self.local_samplers_to_be_rstart = []
        self.goalPt = goalPt
        self.args = args

    def add_to_restart(self, lsampler):
        if lsampler not in self.local_samplers_to_be_rstart:
            self.local_samplers_to_be_rstart.append(lsampler)

    def init_energy(self):
        self.dtrees_energy = np.ones(self.num_dtrees)
        self.dtrees_energy *= ENERGY_START
        self.resync_prob()

    def modify_energy(self, idx=None, particle_ref=None, factor=None, set_val=None):
        # TODO: sometimes the keep tracking might go out of sync (and cause error in np.random.choice. Investigate this)
        # keep track how much energy this operation would modify,
        # so we can change the energy_sum accordingly
        if idx is None:
            # get idx from particle ref
            try:
                idx = self.particles.index(particle_ref)
            except ValueError:
                return
        old_energy = self.dtrees_energy[idx]
        if set_val is not None:
            self.dtrees_energy[idx] = set_val
        elif factor is not None:
            self.dtrees_energy[idx] *= factor
        else:
            raise Exception("Nothing set in modify_energy")

        delta = self.dtrees_energy[idx] - old_energy
        self.cur_energy_sum += delta

    def confirm(self, idx, pos):
        self.particles[idx].confirm(pos)

    def new_pos(self, idx, pos, dir):
        return self.particles[idx].try_new_pos((pos[0], pos[1]), dir)

    def get_pos(self, idx):
        return self.particles[idx].pos

    def get_dir(self, idx):
        return self.particles[idx].direction

    def get_prob(self):
        return self.dtrees_energy / self.cur_energy_sum

    def resync_prob(self):
        self.dtrees_energy = np.nan_to_num(self.dtrees_energy)
        if self.dtrees_energy.sum() < 1e-10:
            # particle_energy demonlished to 0...
            # work around to add energy all particles
            self.dtrees_energy[:] = 1
        self.cur_energy_sum = self.dtrees_energy.sum()

    def new_pos_in_free_space(self):
        """Return a particle that is in free space (from map)"""
        self.args.env.stats.lscampler_restart_counter += 1
        while True:

            new_p = self.randomSampler.get_next_pos()[0]

            self.args.env.stats.add_sampled_node(new_p)
            if not self.args.env.cc.feasible(new_p):
                self.args.env.stats.add_invalid(obs=True)
            else:
                self.args.env.stats.add_free()
                break
        return new_p
