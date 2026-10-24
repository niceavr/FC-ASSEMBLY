#Single Inheritance
class Student:
    def setRno(self,rno):
        self.rno=rno
    def setName(self,name):
        self.name=name
    def setCourse(self,course):
        self.course=course
    def setAds(self,ads):
        self.ads=ads
    def setEmail(self,email):
        self.email=email
    def getRno(self):
        return self.rno
    def getName(self):
        return self.name
    def getCourse(self):
        return self.course
    def getAds(self):
        return self.ads
    def getEmail(self):
        return self.email
class Teacher(Student):
    def setSalary(self,salary):
        self.salary=salary
    def getSalary(self):
        return self.salary
obj=Teacher()
obj.setRno(14)
obj.setName("Venkat")
obj.setCourse("Python")
obj.setAds("Kavali")
obj.setEmail("niceavr@gmail.com")
obj.setSalary(9000)
print("Roll no =",obj.getRno())
print("Name=",obj.getName())
print("Course=",obj.getCourse())
print("Address=",obj.getAds())
print("Email=",obj.getEmail())
print("Salary =",obj.getSalary())       
