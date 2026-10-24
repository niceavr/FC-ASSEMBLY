#Demo of Multilevel inheritance 
class Square:
    def sinput(self,l):
        self.l=l
    def sarea(self):
        self.area=self.l*self.l
        print("Area of the square is ",self.area)
class Rect(Square):
    def rinput(self,l,b):
         self.sinput(l)
         self.b=b
    def rarea(self):
        self.area=self.l*self.b
        print("ARea of the rectangle is",self.area)
class Box(Rect):
    def binput(self,l,b,h):
        self.rinput(l,b)
        self.h=h
    def volume(self):
        self.vol=self.l*self.b*self.h
        print("Volume of a box is",self.vol)
bo=Box()
bo.binput(5,6,9)
bo.volume()
        
    
