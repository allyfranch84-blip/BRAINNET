import unittest
from PIL import Image, ImageDraw
from visual_goal_verifier import verify_new_red_circle
class CanvasGoalTests(unittest.TestCase):
 def setUp(self):self.before=Image.new('RGB',(120,120),'white');self.rect=(0,0,120,120)
 def image(self,shape,color,fill=None):
  im=self.before.copy();d=ImageDraw.Draw(im);getattr(d,shape)((30,30,90,90),outline=color,fill=fill,width=3);return im
 def test_red_circle_outline(self):self.assertTrue(verify_new_red_circle(self.before,self.image('ellipse','red'),self.rect))
 def test_red_circle_filled(self):self.assertTrue(verify_new_red_circle(self.before,self.image('ellipse','red','red'),self.rect))
 def test_red_rectangle_rejected(self):self.assertFalse(verify_new_red_circle(self.before,self.image('rectangle','red'),self.rect))
 def test_blue_circle_rejected(self):self.assertFalse(verify_new_red_circle(self.before,self.image('ellipse','blue'),self.rect))
 def test_missing_canvas_not_verified(self):self.assertFalse(verify_new_red_circle(self.before,self.image('ellipse','red'),None))
if __name__=='__main__':unittest.main()
