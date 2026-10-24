/*Input purchase amount.if purchase amount>=5000 then discount is 30% in purchase amount otherwise discount is
10% in purchase amount.To find and print discount and net amount */
#include<stdio.h>
int main()
{
  float pa,dis,net;
  printf("Enter purchase amount\n") ;
  scanf("%f",&pa);
  if(pa>=5000)
  {
  	dis=pa*30/100;
  }
  if(pa<5000)
  {
  	dis=pa*10/100;
  }
  net=pa-dis;
  printf("\npa =%.2f , discount =%.2f , net amount =%.2f",pa,dis,net);
}
