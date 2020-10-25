from abc import ABC, abstractmethod

import numpy as np


class CollisionChecker(ABC):

    @abstractmethod
    def get_dimension(self):
        pass

    def visible(self, posA, posB):
        pass

    def feasible(self, p):
        pass

    def get_image_shape(self):
        return None

class ImgCollisionChecker(CollisionChecker):

    def __init__(self, img):
        """Short summary.

        Parameters
        ----------
        img : str
            Filename of the image where white pixel represents free space.
        """
        from PIL import Image
        image = Image.open(img).convert('L')
        image = np.array(image)
        image = image / 255
        # white pixxel should now have value of 1
        image[image != 1.0] = 0

        # import matplotlib.pyplot as plt
        # plt.imshow(image)
        # plt.colorbar()

        # need to transpose because pygame has a difference coordinate system than matplotlib matrix
        self.img = image.T

    def get_image_shape(self):
        return self.img.shape

    def get_dimension(self):
        return 2

    def get_coor_before_collision(self, posA, posB):
        pixels = self._get_line(posA, posB)
        # check that all pixel are white (free space)
        endPos = posB
        for p in pixels:
            endPos = (p[0], p[1])
            if not self.feasible(p):
                break
        return endPos

    def visible(self, posA, posB):
        try:
            # get list of pixel between node A and B
            # pixels = lineGenerationAlgorithm(posA, posB)
            pixels = self._get_line(posA, posB)
            # check that all pixel are white (free space)
            for p in pixels:
                if not self.feasible(p):
                    return False
        except ValueError:
            return False
        return True

    def feasible(self, p):
        """check if point is white (which means free space)"""
        try:
            return self.img[tuple(map(int, p))] == 1
        except IndexError:
            return False

    @staticmethod
    def _get_line(start, end):
        """Bresenham's Line Algorithm
        Produces a list of tuples from start and end

        >>> points1 = get_line((0, 0), (3, 4))
        >>> points2 = get_line((3, 4), (0, 0))
        >>> assert(set(points1) == set(points2))
        >>> print points1
        [(0, 0), (1, 1), (1, 2), (2, 3), (3, 4)]
        >>> print points2
        [(3, 4), (2, 3), (1, 2), (1, 1), (0, 0)]
        http://www.roguebasin.com/index.php?title=Bresenham%27s_Line_Algorithm
        """
        # Setup initial conditions
        x1, y1 = map(int, start)
        x2, y2 = map(int, end)
        dx = x2 - x1
        dy = y2 - y1

        # Determine how steep the line is
        is_steep = abs(dy) > abs(dx)

        # Rotate line
        if is_steep:
            x1, y1 = y1, x1
            x2, y2 = y2, x2

        # Swap start and end points if necessary and store swap state
        swapped = False
        if x1 > x2:
            x1, x2 = x2, x1
            y1, y2 = y2, y1
            swapped = True

        # Recalculate differentials
        dx = x2 - x1
        dy = y2 - y1

        # Calculate error
        error = int(dx / 2.0)
        ystep = 1 if y1 < y2 else -1

        # Iterate over bounding box generating points between start and end
        y = y1
        points = []
        for x in range(x1, x2 + 1):
            coord = (y, x) if is_steep else (x, y)
            points.append(coord)
            error -= abs(dy)
            if error < 0:
                y += ystep
                error += dx

        # Reverse the list if the coordinates were swapped
        if swapped:
            points.reverse()
        return points


class KlamptCollisionChecker(CollisionChecker):

    def __init__(self, xml, stats):
        self.stats = stats
        import klampt
        from klampt.plan import robotplanning
        from klampt.io import resource

        world = klampt.WorldModel()
        world.readFile(xml)  # very cluttered
        robot = world.robot(0)

        # this is the CSpace that will be used.  Standard collision and joint limit constraints
        # will be checked
        space = robotplanning.makeSpace(world, robot, edgeCheckResolution=0.1)

        # fire up a visual editor to get some start and goal configurations
        qstart = robot.getConfig()
        qgoal = robot.getConfig()

        self.space = space
        self.robot = robot
        self.world = world

        import copy
        self.template_pos = copy.copy(qstart)
        self.template_pos[1:7] = [0] * 6

        self.qstart = self._translate_from_klampt(qstart)
        self.qgoal = self._translate_from_klampt(qgoal)

    def get_dimension(self):
        return 6

    def get_dimension_limits(self):
        return self.robot.getJointLimits()

    def _translate_to_klampt(self, p):
        assert len(p) == 6
        import copy
        new_pos = list(self.template_pos)
        new_pos[1:7] = p
        return new_pos

    def _translate_from_klampt(self, p):
        assert len(p) == 12, len(p)
        return p[1:7]

    def visible(self, a, b):
        a = self._translate_to_klampt(a)
        b = self._translate_to_klampt(b)
        # print(self.space.visible(a, b))
        self.stats.visible_cnt += 1
        return self.space.isVisible(a, b)

    def feasible(self, p):
        p = self._translate_to_klampt(p)
        self.stats.feasible_cnt += 1
        return self.space.feasible(p)