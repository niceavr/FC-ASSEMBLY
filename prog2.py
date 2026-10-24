#constructor with arguments :various objects with various data
class Student:
    def __init__(self,name,age):
        self.name=name
        self.age=age
    def talk(self):
        print(f"Hi {self.name} , your age is : {self.age}")
rama=Student("Rama",45)
rama.talk()

sita=Student("Sitha",35)
sita.talk()

anji=Student("Anji",90)
anji.talk()
